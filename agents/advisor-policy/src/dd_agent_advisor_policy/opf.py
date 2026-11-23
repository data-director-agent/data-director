"""Jisc Open Policy Finder: funder, publisher and journal open access policies, read live.

Open Policy Finder (https://openpolicyfinder.jisc.ac.uk) replaced Sherpa Romeo, Juliet and Fact
in 2024. Its API platform (`https://api.openpolicyfinder.jisc.ac.uk`) needs a free key, sent in
the `x-api-key` header, never in the query string, so it stays out of access logs:

- `GET /retrieve?item-type=<type>&format=Json&limit=<n>&filter=[["field","operator","value"]]`
  lists records of one type (`publication`, that is a journal, `publisher` or `funder`).
- `GET /retrieve_by_id?item-type=<type>&format=Json&identifier=<id>` reads one record, by its
  Open Policy Finder identifier or, for a publication, by an ISSN.

The records describe open access policy: where a version of an article may be deposited, after
what embargo and under which licence (Romeo), and what a funder requires of its outputs,
including any data archiving requirement (Juliet). A journal's record links to its publishers'.

It is read live only. Jisc licenses the data under CC BY-NC-ND 4.0, and the API is for
non-commercial use. No-derivatives rules out the projected registry a snapshot would be built
into, and Jisc states no rate limit, so there is no snapshot to fall back to: when the route
fails, the agent says so and carries on with FAIRsharing (docs/specs/dependencies.md).

The requests follow Jisc's developer documentation
(https://openpolicyfinder.jisc.ac.uk/help/developers/api-types/object-retrieval-api): the item
types, the filter fields (`name` and `acronym` for funders and publishers, `title` and `acronym`
for journals), the operators (`equals`, `contains word`, `gte`, `lte`), at most three conditions,
all of which must hold, and the answer's `items`. The table of parameters still lists `format`
as required while another note says it is ignored, so it is sent. TODO(#302): confirm with a key
where a funder's record keeps its policies (`POLICY_KEYS`) and record the test fixtures; the
parser reads the shape of the Sherpa v2 API, which Jisc says the platform replicates, and keeps
any field it does not know as it came.

Each record is projected to `OpfRecord`, hashed whole under `dd-json-document-v1` like a
FAIRsharing record. Numbers are kept as strings, since the A2A transport would turn them into
doubles and change the hash (records.py).

Any transport failure, error status or unreadable answer raises `RegistryUnavailable`; an
unknown identifier is None. Run `python -m dd_agent_advisor_policy.opf check` with
`OPEN_POLICY_FINDER_API_KEY` set to try the route against a few known records.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from dd_agent_advisor_policy.records import prompt_json
from dd_agent_advisor_policy.ror import USER_AGENT
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash
from dd_sdk.registry import RegistryUnavailable, SnapshotRef

API_BASE = "https://api.openpolicyfinder.jisc.ac.uk"
RETRIEVE = f"{API_BASE}/retrieve"
RETRIEVE_BY_ID = f"{API_BASE}/retrieve_by_id"
PUBLIC_URL = "https://openpolicyfinder.jisc.ac.uk/{item_type}/{id}"
REGISTRY_LABEL = "open-policy-finder"
TIMEOUT_S = 20.0
SEARCH_LIMIT = 10
# The most characters of one record's policy text a model is shown.
PROMPT_CHARS = 6000

type ItemType = Literal["publication", "publisher", "funder"]
ITEM_TYPES: tuple[ItemType, ...] = ("publication", "publisher", "funder")
# Where a record keeps its policies: a journal's publisher policies, or a funder's own.
POLICY_KEYS = ("publisher_policy", "policies", "policy", "funder_policy")
# The documented filter field that holds a record's name, and the one that holds its acronym.
NAME_FIELD: dict[ItemType, str] = {"publication": "title", "publisher": "name", "funder": "name"}
ACRONYM_FIELD = "acronym"
# The documented operator that matches a whole word, and the most conditions one filter holds.
OPERATOR = "contains word"
MAX_CONDITIONS = 3
# Words left out of a filter: they say little about which record is meant.
CONNECTING_WORDS = frozenset(
    {"a", "an", "and", "at", "de", "der", "des", "du", "et", "for", "für", "in", "of", "on"}
    | {"the", "to", "und"}
)
_WORD = re.compile(r"\w+")
_ACRONYM = re.compile(r"[A-Z][A-Z0-9]{1,9}")


def filter_for(item_type: ItemType, text: str) -> str:
    """The `filter` of a search for records of `item_type` named `text`: a single word in
    capitals, such as "NERC", is looked for among acronyms; otherwise up to three of the name's
    longest words, leaving out connecting words, must each be a whole word of the name. The
    caller keeps only the records whose names match exactly."""
    words = _WORD.findall(text)
    if len(words) == 1 and _ACRONYM.fullmatch(words[0]):
        return json.dumps([[ACRONYM_FIELD, OPERATOR, words[0]]])
    telling = [w for w in words if w.casefold() not in CONNECTING_WORDS] or words[:1]
    longest = sorted(range(len(telling)), key=lambda i: -len(telling[i]))[:MAX_CONDITIONS]
    field = NAME_FIELD[item_type]
    return json.dumps([[field, OPERATOR, telling[i]] for i in sorted(longest)], ensure_ascii=False)


def _stringified(value: Any) -> Any:
    """`value` with every number and boolean as a string, so the document hashes alike after the
    A2A transport, and empty values dropped."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        out = {str(k): _stringified(v) for k, v in value.items()}
        return {k: v for k, v in out.items() if v not in (None, "", [], {})}
    if isinstance(value, list):
        items = [_stringified(v) for v in value]
        return [v for v in items if v not in (None, "", [], {})]
    return None


def _texts(value: Any, key: str) -> list[str]:
    """The strings under `key` in a list of `{key: ...}` objects, a list of strings or a string."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get(key), str) and item[key].strip():
            out.append(item[key].strip())
        elif isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _unique(values: Sequence[str]) -> list[str]:
    seen: dict[str, str] = {}
    for v in values:
        seen.setdefault(v.casefold(), v)
    return list(seen.values())


class OpfLink(BaseModel):
    """A link from a journal's record to one of its publishers'."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str | None = None
    relationship: str | None = None


class OpfRecord(BaseModel):
    """One Open Policy Finder record, as this agent keeps it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_type: ItemType
    id: str
    names: list[str] = Field(default_factory=list)
    acronyms: list[str] = Field(default_factory=list)
    country: str | None = None
    url: str | None = None
    issns: list[str] = Field(default_factory=list)
    publishers: list[OpfLink] = Field(default_factory=list)
    identifiers: list[Any] = Field(default_factory=list)
    # The policies as the record states them, numbers as strings.
    policies: list[Any] = Field(default_factory=list)

    # What every source record offers the agent (retrieve.SourceRecord).
    registry: ClassVar[str] = "Open Policy Finder"

    @property
    def source_id(self) -> str:
        return PUBLIC_URL.format(item_type=self.item_type, id=self.id)

    @property
    def source_uri(self) -> str:
        return self.source_id

    @property
    def name(self) -> str:
        return self.names[0] if self.names else f"{self.item_type} {self.id}"

    @property
    def label(self) -> str:
        return f"{self.name} (Open Policy Finder {self.item_type} {self.id})"

    @property
    def kind(self) -> str:
        """What the record is a policy of, in FAIRsharing's terms where they agree."""
        return {"publication": "journal", "publisher": "journal_publisher"}.get(
            self.item_type, self.item_type
        )

    def all_names(self) -> list[str]:
        return [n.casefold() for n in (*self.names, *self.acronyms)]

    def document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def content_hash(self) -> str:
        return content_hash(self.document(), DOCUMENT_CANONICALISATION)

    def prompt_text(self, limit: int = PROMPT_CHARS) -> str:
        return prompt_json(self.document(), limit)


def from_item(item: dict[str, Any], item_type: ItemType) -> OpfRecord | None:
    """A record from one item of an answer. None if it has no identifier."""
    raw_meta = item.get("system_metadata")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    raw_id = item.get("id", meta.get("id"))
    if raw_id is None or str(raw_id).strip() == "":
        return None
    names = _texts(item.get("title"), "title") + _texts(item.get("name"), "name")
    acronyms = _texts(item.get("name"), "acronym") + _texts(item.get("acronym"), "acronym")
    urls = _texts(item.get("url"), "url") + _texts(meta.get("uri"), "uri")
    publishers: list[OpfLink] = []
    for link in item.get("publishers") or []:
        if not isinstance(link, dict):
            continue
        nested = link.get("publisher")
        publisher: dict[str, Any] = nested if isinstance(nested, dict) else link
        pid = publisher.get("id")
        if pid is None:
            continue
        pname = _texts(publisher.get("name"), "name")
        publishers.append(
            OpfLink(
                id=str(pid),
                name=pname[0] if pname else None,
                relationship=link.get("relationship_type") or None,
            )
        )
    policies: list[Any] = []
    for key in POLICY_KEYS:
        value = item.get(key)
        if isinstance(value, list):
            policies.extend(value)
        elif isinstance(value, dict):
            policies.append(value)
    country = item.get("country")
    return OpfRecord(
        item_type=item_type,
        id=str(raw_id),
        names=_unique(names),
        acronyms=_unique(acronyms),
        country=country.strip() if isinstance(country, str) and country.strip() else None,
        url=urls[0] if urls else None,
        issns=sorted({i.upper() for i in _texts(item.get("issns"), "issn")}),
        publishers=sorted(set(publishers), key=lambda p: p.id),
        identifiers=_stringified(item.get("identifiers") or []),
        policies=_stringified(policies),
    )


class OpenPolicyFinder:
    """The live API. One instance serves concurrent runs: it keeps no per-run state."""

    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        now: datetime | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Open Policy Finder needs an API key")
        self._key = api_key
        self._client = client
        self._now = now

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT})
        return self._client

    def snapshot_ref(self) -> SnapshotRef:
        now = self._now or datetime.now(UTC)
        return SnapshotRef(
            label=f"{REGISTRY_LABEL}:live:{now.date().isoformat()}",
            fetched_at=now.isoformat(timespec="seconds"),
        )

    def _items(self, url: str, params: dict[str, str]) -> list[dict[str, Any]] | None:
        """The items of one answer; None for a 404. The key goes in a header, never in `params`."""
        try:
            resp = self._http().get(
                url,
                params={"format": "Json", **params},
                headers={"x-api-key": self._key, "User-Agent": USER_AGENT},
            )
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"Open Policy Finder: {type(exc).__name__}") from None
        if resp.status_code == 404:
            return None
        if resp.status_code in (401, 403):
            raise RegistryUnavailable(
                f"Open Policy Finder: HTTP {resp.status_code}; check OPEN_POLICY_FINDER_API_KEY"
            )
        if resp.status_code != 200:
            raise RegistryUnavailable(f"Open Policy Finder: HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError:
            raise RegistryUnavailable("Open Policy Finder: an answer that is not JSON") from None
        items = body.get("items") if isinstance(body, dict) else body
        if not isinstance(items, list):
            raise RegistryUnavailable("Open Policy Finder: an answer with no items")
        return [i for i in items if isinstance(i, dict)]

    def _records(self, items: list[dict[str, Any]] | None, item_type: ItemType) -> list[OpfRecord]:
        found = [from_item(i, item_type) for i in items or []]
        unique = {r.id: r for r in found if r is not None}
        return list(unique.values())

    def search(self, item_type: ItemType, text: str, limit: int = SEARCH_LIMIT) -> list[OpfRecord]:
        """Records of `item_type` whose name (a journal's title) has the telling words of `text`
        (`filter_for`)."""
        query = filter_for(item_type, text)
        items = self._items(
            RETRIEVE, {"item-type": item_type, "limit": str(limit), "filter": query}
        )
        return self._records(items, item_type)

    def fetch(self, item_type: ItemType, identifier: str) -> OpfRecord | None:
        """One record by its identifier (or, for a journal, an ISSN). None if there is none."""
        items = self._items(
            RETRIEVE_BY_ID, {"item-type": item_type, "identifier": identifier.strip()}
        )
        records = self._records(items, item_type)
        return records[0] if records else None

    def journal_by_issn(self, issn: str) -> OpfRecord | None:
        return self.fetch("publication", issn)


# --- the route check, to be run with a key ------------------------------------------------

# Records that should be found, chosen from the pilot workshop's cases (#750, #905).
CHECKS: tuple[tuple[str, ItemType, str], ...] = (
    ("search", "funder", "Natural Environment Research Council"),
    ("search", "funder", "Economic and Social Research Council"),
    ("search", "publisher", "Elsevier"),
    ("search", "publication", "Science of the Total Environment"),
    ("fetch", "publication", "0048-9697"),
)


def check(api_key: str, record_to: Path | None = None) -> int:
    """Ask the live route for each of `CHECKS` and say what came back. With `record_to`, write
    each raw answer there, for use as a test fixture once read and trimmed."""
    client = httpx.Client(timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT})
    source = OpenPolicyFinder(api_key, client=client)
    failures = 0
    for n, (how, item_type, text) in enumerate(CHECKS, start=1):
        try:
            if how == "search":
                found = source.search(item_type, text)
            else:
                one = source.fetch(item_type, text)
                found = [one] if one else []
        except RegistryUnavailable as exc:
            failures += 1
            sys.stdout.write(f"{how} {item_type} {text!r}: unavailable ({exc})\n")
            continue
        names = "; ".join(r.label for r in found[:5]) or "(none)"
        policies = sum(len(r.policies) for r in found)
        sys.stdout.write(
            f"{how} {item_type} {text!r}: {len(found)} record(s), {policies} policies: {names}\n"
        )
        if record_to is not None:
            record_to.mkdir(parents=True, exist_ok=True)
            out = record_to / f"opf-check-{n}-{item_type}.json"
            out.write_text(
                json.dumps([r.document() for r in found], indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m dd_agent_advisor_policy.opf",
        description="Check the Open Policy Finder route with OPEN_POLICY_FINDER_API_KEY.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("check", help="ask the live API for a few known records")
    run.add_argument("--record", type=Path, help="write each answer, as projected, to this folder")
    args = parser.parse_args(argv)
    from dd_sdk.credentials import ConfigError, api_key

    try:
        key = api_key(dict(os.environ), "OPEN_POLICY_FINDER_API_KEY")
    except ConfigError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return check(key, args.record)


if __name__ == "__main__":
    raise SystemExit(main())

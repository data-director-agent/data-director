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
non-commercial use, so nothing is kept: no cache, no snapshot. Jisc states no rate limit.

The requests follow Jisc's developer documentation
(https://openpolicyfinder.jisc.ac.uk/help/developers/api-types/object-retrieval-api): the item
types, the filter fields (`name` and `acronym` for funders and publishers, `title` and `acronym`
for journals), the operators (`equals`, `contains word`, `gte`, `lte`), at most three conditions,
all of which must hold, and the answer's `items`. The table of parameters still lists `format`
as required while another note says it is ignored, so it is sent. The parser reads the shape of
the Sherpa v2 API, which Jisc says the platform replicates, and keeps any field it does not know
as it came. It was written without a key: `dd-mcp-opf check` tries the route with one, and
`POLICY_KEYS`, where a funder's record keeps its policies, is not yet confirmed.

A record is a plain dict (`record_from_item`). It holds no integers (a number or a flag is a
string), so that it hashes the same after a round trip through a format whose numbers are doubles.
Any transport failure, error status or unreadable answer raises `OpfUnavailableError`; an unknown
identifier is None.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

import httpx

API_BASE = "https://api.openpolicyfinder.jisc.ac.uk"
RETRIEVE = f"{API_BASE}/retrieve"
RETRIEVE_BY_ID = f"{API_BASE}/retrieve_by_id"
PUBLIC_URL = "https://openpolicyfinder.jisc.ac.uk/{item_type}/{id}"
SOURCE_URL = "https://github.com/data-director-agent/data-director"
KEY_NAME = "OPEN_POLICY_FINDER_API_KEY"
TIMEOUT_S = 20.0
SEARCH_LIMIT = 10

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
# A plain address: nothing that could end the User-Agent's comment or start another header.
ADDRESS = re.compile(r"[^\s@<>();,\"\\]+@[^\s@<>();,\"\\]+\.[^\s@<>();,\"\\]+")
_ISSN = re.compile(r"(?P<head>\d{4})-?(?P<tail>\d{3}[\dX])")


class OpfUnavailableError(Exception):
    """Open Policy Finder could not be asked, or gave an answer that cannot be read. The message
    says why and holds nothing the caller sent, and never the key."""


def normal_issn(value: str) -> str | None:
    """`value` as `NNNN-NNNC`, or None if it is not an ISSN."""
    found = _ISSN.fullmatch(value.strip().upper())
    return f"{found['head']}-{found['tail']}" if found else None


def _package_version() -> str:
    try:
        return version("data-director-mcp-opf")
    except PackageNotFoundError:  # pragma: no cover - run from a source tree without installing
        return "0"


def user_agent(contact: str | None = None) -> str:
    """This package's User-Agent, with `mailto:contact` when a contact address is given. Raises
    `ValueError` when `contact` is not one plain address."""
    if contact is not None and ADDRESS.fullmatch(contact) is None:
        raise ValueError(f"{contact!r} is not an e-mail address")
    comment = [f"+{SOURCE_URL}", *([f"mailto:{contact}"] if contact else [])]
    return f"data-director-mcp-opf/{_package_version()} ({'; '.join(comment)})"


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
    """`value` with every number and boolean as a string, so the document hashes alike after a
    transport whose numbers are doubles, and empty values dropped."""
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


def _publisher_links(item: dict[str, Any]) -> list[dict[str, Any]]:
    """The publishers a journal's record links to, by identifier."""
    links: dict[str, dict[str, Any]] = {}
    for link in item.get("publishers") or []:
        if not isinstance(link, dict):
            continue
        nested = link.get("publisher")
        publisher: dict[str, Any] = nested if isinstance(nested, dict) else link
        pid = publisher.get("id")
        if pid is None:
            continue
        pname = _texts(publisher.get("name"), "name")
        links[str(pid)] = {
            "id": str(pid),
            "name": pname[0] if pname else None,
            "relationship": link.get("relationship_type") or None,
        }
    return [links[k] for k in sorted(links)]


def record_from_item(item: dict[str, Any], item_type: ItemType) -> dict[str, Any] | None:
    """One item of an answer as a record. None if it has no identifier.

    `page` is the record's public page, to cite; the rest is what the record says."""
    raw_meta = item.get("system_metadata")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    raw_id = item.get("id", meta.get("id"))
    if raw_id is None or str(raw_id).strip() == "":
        return None
    names = _texts(item.get("title"), "title") + _texts(item.get("name"), "name")
    acronyms = _texts(item.get("name"), "acronym") + _texts(item.get("acronym"), "acronym")
    urls = _texts(item.get("url"), "url") + _texts(meta.get("uri"), "uri")
    policies: list[Any] = []
    for key in POLICY_KEYS:
        value = item.get(key)
        if isinstance(value, list):
            policies.extend(value)
        elif isinstance(value, dict):
            policies.append(value)
    country = item.get("country")
    return {
        "item_type": item_type,
        "id": str(raw_id),
        "page": PUBLIC_URL.format(item_type=item_type, id=str(raw_id)),
        "names": _unique(names),
        "acronyms": _unique(acronyms),
        "country": country.strip() if isinstance(country, str) and country.strip() else None,
        "url": urls[0] if urls else None,
        "issns": sorted({i.upper() for i in _texts(item.get("issns"), "issn")}),
        "publishers": _publisher_links(item),
        "identifiers": _stringified(item.get("identifiers") or []),
        "policies": _stringified(policies),
    }


class OpenPolicyFinder:
    """The live API. One instance serves concurrent calls: it keeps no per-call state."""

    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        contact: str | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Open Policy Finder needs an API key")
        self._key = api_key
        self._client = client
        self._agent = user_agent(contact)

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=TIMEOUT_S, headers={"User-Agent": self._agent})
        return self._client

    def _items(self, url: str, params: dict[str, str]) -> list[dict[str, Any]] | None:
        """The items of one answer; None for a 404. The key goes in a header, never in `params`."""
        try:
            resp = self._http().get(
                url,
                params={"format": "Json", **params},
                headers={"x-api-key": self._key, "User-Agent": self._agent},
            )
        except httpx.HTTPError as exc:
            raise OpfUnavailableError(f"Open Policy Finder: {type(exc).__name__}") from None
        if resp.status_code == 404:
            return None
        if resp.status_code in (401, 403):
            raise OpfUnavailableError(
                f"Open Policy Finder: HTTP {resp.status_code}; check {KEY_NAME}"
            )
        if resp.status_code != 200:
            raise OpfUnavailableError(f"Open Policy Finder: HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError:
            raise OpfUnavailableError("Open Policy Finder: an answer that is not JSON") from None
        items = body.get("items") if isinstance(body, dict) else body
        if not isinstance(items, list):
            raise OpfUnavailableError("Open Policy Finder: an answer with no items")
        return [i for i in items if isinstance(i, dict)]

    @staticmethod
    def _records(items: list[dict[str, Any]] | None, item_type: ItemType) -> list[dict[str, Any]]:
        found = [record_from_item(i, item_type) for i in items or []]
        unique = {r["id"]: r for r in found if r is not None}
        return list(unique.values())

    def search(
        self, item_type: ItemType, text: str, limit: int = SEARCH_LIMIT
    ) -> list[dict[str, Any]]:
        """Records of `item_type` whose name (a journal's title) has the telling words of `text`
        (`filter_for`)."""
        query = filter_for(item_type, text)
        items = self._items(
            RETRIEVE, {"item-type": item_type, "limit": str(limit), "filter": query}
        )
        return self._records(items, item_type)

    def fetch(self, item_type: ItemType, identifier: str) -> dict[str, Any] | None:
        """One record by its identifier (or, for a journal, an ISSN). None if there is none."""
        items = self._items(
            RETRIEVE_BY_ID, {"item-type": item_type, "identifier": identifier.strip()}
        )
        records = self._records(items, item_type)
        return records[0] if records else None

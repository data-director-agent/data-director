"""Crossref's journal records: which publisher a journal belongs to.

Most journals have no data policy of their own in FAIRsharing: they follow their publisher's. A
journal is therefore identified in Crossref first (https://api.crossref.org/journals), by its ISSN
when the researcher gives one, otherwise by its exact title. The publisher Crossref records for
it is then searched in FAIRsharing as well as the journal's own title, so that a journal finds its
publisher's policy without anyone keeping a table of journals or publishers.

`CrossrefJournals` asks Crossref's REST API, which needs no account. Its records are open metadata
that Crossref places in the public domain. There is no pinned copy yet: evidence from this route
is labelled `crossref:live:<date>`, which the harness's source check reports as unresolved, as it
does every live route (docs/specs/grounding.md).

A title is matched exactly, ignoring case and spacing; Crossref's search is fuzzy, so its results
are filtered here. Only the first page of results is read, so a very common title may need its
ISSN.

Like `ror.py`, this module does not use the Data Director contract. It is one of the importers of
`httpx` (docs/specs/dependencies.md).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from dd_agent_advisor_policy.retrieve import RegistryUnavailable, SnapshotRef

API_BASE = "https://api.crossref.org/journals"
LIVE_TIMEOUT_S = 20.0
# Search results read for a title: Crossref's search is fuzzy, and the exact title is usually
# among the first.
SEARCH_ROWS = 20
REGISTRY_LABEL = "crossref"

# An ISSN: four digits, a hyphen, three digits and a check character.
ISSN = re.compile(r"^(\d{4})-?(\d{3}[\dXx])$")
# The legal form at the end of a company's name ("Elsevier BV", "Wiley-Blackwell Ltd."), which
# FAIRsharing's policy names leave out. A rule about company names, not a list of publishers.
_LEGAL_FORM = re.compile(
    r"[\s,]+(?:b\.?\s?v\.?|n\.?\s?v\.?|ltd\.?|limited|inc\.?|incorporated|llc|l\.l\.c\.|plc|"
    r"gmbh|ag|s\.?\s?a\.?|s\.?\s?l\.?|s\.?\s?r\.?\s?l\.?|co\.?|corp\.?|corporation|"
    r"sp\.?\s?z\s?o\.?\s?o\.?|kft\.?|pty\.?|a/s|ab|oy)\s*$",
    re.IGNORECASE,
)


def _user_agent() -> str:
    """Names the project and where to find it, never a person."""
    try:
        ours = version("data-director-agent-advisor-policy")
    except PackageNotFoundError:
        ours = "unknown"
    return (
        f"data-director-advisor-policy/{ours} "
        "(+https://github.com/data-director-agent/data-director)"
    )


def issn(value: str) -> str | None:
    """`value` as an ISSN in its usual form (`0022-1694`), or None if it is not one."""
    found = ISSN.match(value.strip())
    return f"{found.group(1)}-{found.group(2).upper()}" if found else None


def normalise(title: str) -> str:
    """A title as it is matched: case-folded, with runs of spaces made one."""
    return " ".join(title.casefold().split())


def without_legal_form(name: str) -> str:
    """A company's name without its legal form, repeatedly ("Foo Publishing Co. Ltd" -> "Foo
    Publishing"); the name itself if it has none."""
    out = name.strip()
    while True:
        shorter = _LEGAL_FORM.sub("", out).strip(" ,")
        if shorter == out or not shorter:
            return out
        out = shorter


_BRACKETED = re.compile(r"\s*\([^()]*\)\s*$")


def publisher_forms(name: str) -> list[str]:
    """The forms of a publisher's name FAIRsharing may know it by: as Crossref gives it, without
    its legal form, and without a closing bracket that names an imprint or an abbreviation
    ("Wiley (Blackwell Publishing)" as "Wiley"). Each once, in that order."""
    forms = [name.strip(), without_legal_form(name)]
    forms += [without_legal_form(_BRACKETED.sub("", f)) for f in forms]
    out: list[str] = []
    for form in forms:
        if form and form.casefold() not in {o.casefold() for o in out}:
            out.append(form)
    return out


class Journal(BaseModel):
    """A journal as Crossref records it, cut to what identifying its publisher needs. What is
    hashed and shown as evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    """`https://api.crossref.org/journals/<ISSN>`, for the first of its ISSNs: what the payload
    cites."""
    title: str
    publisher: str | None = None
    issns: list[str] = Field(default_factory=list)

    @field_validator("issns")
    @classmethod
    def _sort(cls, values: list[str]) -> list[str]:
        return sorted(set(values))

    def document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def matches(self, title: str) -> bool:
        return normalise(self.title) == normalise(title)


def from_crossref_json(item: dict[str, Any]) -> Journal:
    """One journal from Crossref's `message` (or one of its search `items`). Raises
    `ValidationError`, `KeyError` or `TypeError` for a record that cannot be read."""
    issns = sorted({i for i in (issn(str(v)) for v in item.get("ISSN") or []) if i})
    if not issns:
        raise KeyError("ISSN")
    publisher = item.get("publisher")
    return Journal(
        id=f"{API_BASE}/{issns[0]}",
        title=str(item["title"]).strip(),
        publisher=str(publisher).strip() if publisher else None,
        issns=issns,
    )


@runtime_checkable
class Journals(Protocol):
    """Where journals are looked up. Every method raises `RegistryUnavailable` when the copy
    cannot be read, which is not the same as finding nothing."""

    def snapshot_ref(self) -> SnapshotRef: ...

    def get(self, issn: str) -> Journal | None: ...

    def find(self, title: str) -> list[Journal]:
        """The journals whose title is exactly `title`, ignoring case and spacing, by id."""
        ...


class CrossrefJournals:
    """Crossref's REST API. Any transport failure raises `RegistryUnavailable`; the agent then
    searches the journal by the name given and says so."""

    def __init__(self, client: httpx.Client | None = None, now: datetime | None = None) -> None:
        self._client = client
        self._now = now

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=LIVE_TIMEOUT_S,
                headers={"User-Agent": _user_agent()},
                follow_redirects=True,
            )
        return self._client

    def _get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        try:
            return self._http().get(url, params=params)
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"Crossref: {exc}") from None

    def snapshot_ref(self) -> SnapshotRef:
        now = self._now or datetime.now(UTC)
        return SnapshotRef(
            label=f"{REGISTRY_LABEL}:live:{now.date().isoformat()}",
            fetched_at=now.isoformat(timespec="seconds"),
        )

    def get(self, value: str) -> Journal | None:
        wanted = issn(value)
        if wanted is None:
            return None
        resp = self._get(f"{API_BASE}/{wanted}")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise RegistryUnavailable(f"Crossref: HTTP {resp.status_code} for ISSN {wanted}")
        try:
            return from_crossref_json(resp.json()["message"])
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            raise RegistryUnavailable(f"Crossref: an answer that cannot be read ({exc})") from None

    def find(self, title: str) -> list[Journal]:
        if not title.strip():
            return []
        resp = self._get(API_BASE, {"query": title, "rows": str(SEARCH_ROWS)})
        if resp.status_code != 200:
            raise RegistryUnavailable(f"Crossref: HTTP {resp.status_code} for a search")
        try:
            items = resp.json()["message"].get("items") or []
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise RegistryUnavailable(f"Crossref: an answer that cannot be read ({exc})") from None
        found: dict[str, Journal] = {}
        for item in items:
            try:
                journal = from_crossref_json(item)
            except KeyError, TypeError, ValidationError:
                continue  # a record with no ISSN cannot be cited
            if journal.matches(title):
                found.setdefault(journal.id, journal)
        return [found[k] for k in sorted(found)]

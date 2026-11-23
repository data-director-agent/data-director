"""Shared test doubles: the registries served from recorded upstream answers, never the network.

The files in `data/` are real answers, recorded on 19 November 2026 from DataCite
(`/dois/10.15497/rda00157`), Crossref (`/works/10.1038/sdata.2016.18`), ORCID
(`/v3.0/0000-0002-1825-0097/person`, ORCID's test record for Josiah Carberry) and ROR
(`/v2/organizations/02b5d8509`).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx

from dd_journals import Journal
from dd_journals import Registry as JournalIndex
from dd_mcp_pid.caching import Lookups
from dd_mcp_pid.dois import Crossref, DataCite
from dd_mcp_pid.http import Http
from dd_mcp_pid.journals import JournalSource, journal_registry
from dd_mcp_pid.orcid import Orcid
from dd_mcp_pid.ror import RorApi, RorIndex
from dd_mcp_pid.ror_records import from_ror_json
from dd_mcp_pid.tools import Registry, RorSources, doi_registry, orcid_registry, ror_registry

DATA = Path(__file__).with_name("data")

DATACITE_DOI = "10.15497/rda00157"
CROSSREF_DOI = "10.1038/sdata.2016.18"
ORCID_ID = "0000-0002-1825-0097"
NERC = "https://ror.org/02b5d8509"

# Path on each API -> recorded answer.
ANSWERS = {
    "api.datacite.org": {f"/dois/{DATACITE_DOI}": "datacite-10.15497-rda00157.json"},
    "api.crossref.org": {f"/works/{CROSSREF_DOI}": "crossref-10.1038-sdata.2016.18.json"},
    "pub.orcid.org": {f"/v3.0/{ORCID_ID}/person": "orcid-0000-0002-1825-0097.person.json"},
    "api.ror.org": {"/v2/organizations/02b5d8509": "ror-02b5d8509.api.json"},
}


def recorded(request: httpx.Request) -> httpx.Response:
    """The recorded answer to `request`, or 404 as the registries answer an unknown identifier."""
    name = ANSWERS.get(request.url.host, {}).get(request.url.path)
    if name is None:
        return httpx.Response(404, json={"errors": [{"status": "404", "title": "Not found"}]})
    return httpx.Response(200, content=(DATA / name).read_bytes())


def http(name: str, handler: Callable[[httpx.Request], httpx.Response] = recorded) -> Http:
    return Http(name, transport=httpx.MockTransport(handler), sleep=lambda _s: None)


def built_registry(directory: Path) -> Path:
    """A registry of one organisation, NERC, built as the policy advisor builds it."""
    org = from_ror_json(json.loads((DATA / "ror-02b5d8509.api.json").read_text(encoding="utf-8")))
    path = directory / "registry.jsonl"
    path.write_text(json.dumps(org.document(), sort_keys=True) + "\n", encoding="utf-8")
    return path


STOTEN = "0048-9697"
STOTEN_ONLINE = "1879-1026"


def journal(issn_l: str, title: str, works: int, *issns: str, **extra: object) -> Journal:
    fields: dict[str, object] = {
        "issn_l": issn_l,
        "issns": tuple(sorted({issn_l, *issns})),
        "title": title,
        "alternate_titles": (),
        "abbreviated_title": None,
        "publisher": None,
        "country": None,
        "homepage": None,
        "is_in_doaj": False,
        "is_oa": False,
        "openalex_id": f"https://openalex.org/S{issn_l.replace('-', '')}",
        "works_count": works,
    }
    return Journal(**{**fields, **extra})  # type: ignore[arg-type]


JOURNALS = [
    journal(
        STOTEN, "Science of The Total Environment", 90000, STOTEN_ONLINE, publisher="Elsevier BV"
    ),
    journal("0028-0836", "Nature", 400000, "1476-4687", publisher="Springer Nature"),
    journal("1758-678X", "Nature Climate Change", 5000),
    journal("2052-4463", "Scientific Data", 3000, alternate_titles=("Sci Data",), is_oa=True),
]


def built_journals(directory: Path) -> Path:
    """A journal registry of a few journals, indexed as `dd-journals` indexes the real one."""
    path = directory / "journals.sqlite"
    JournalIndex.build(JOURNALS, path, "pinned", "OpenAlex test snapshot")
    return path


def registries(
    registry: Path | None = None,
    handler: Callable[[httpx.Request], httpx.Response] = recorded,
    journals: Path | None = None,
    lookups: Lookups | None = None,
) -> list[Registry]:
    """Every registry, answering from the recorded files (`registry` for ROR, and `journals` for
    the journal registry; a registry not given is not built). `lookups` is the cache they share,
    a new one in memory by default; offline, ROR's API is not given."""
    cached = lookups or Lookups()
    return [
        doi_registry("DataCite", DataCite(http("DataCite", handler)), cached),
        doi_registry("Crossref", Crossref(http("Crossref", handler)), cached),
        orcid_registry(Orcid(http("ORCID", handler)), cached),
        ror_registry(
            RorSources(
                index=RorIndex(registry) if registry else None,
                api=None if cached.offline else RorApi(http("ROR", handler)),
                index_label="ROR dump test",
                lookups=cached,
            )
        ),
        journal_registry(JournalSource(journals or Path("/nonexistent/journals.sqlite"))),
    ]

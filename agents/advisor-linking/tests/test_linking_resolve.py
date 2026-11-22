"""advisor.linking's lookups through the tool gateway, against the PID resolver's own servers
(`dd_mcp_pid`) served in process, with the registries' HTTP replaced by canned answers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from dd_agent_advisor_linking.agent import LinkingAdviser, load_schemes
from dd_agent_advisor_linking.classes import LinkCandidates, RelatedIdentifiers
from dd_harness.gateway.config import ToolServer, tools_digest
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_harness.testing.tools import fake_gateway, tools_profile
from dd_mcp_pid.app import mcp_server
from dd_mcp_pid.dois import Crossref, DataCite
from dd_mcp_pid.http import Http
from dd_mcp_pid.orcid import Orcid
from dd_mcp_pid.ror import RorApi
from dd_mcp_pid.tools import Registry, RorSources, doi_registry, orcid_registry, ror_registry
from dd_sdk.contract.models import Envelope, OutcomeStatus
from dd_sdk.evidence import DOCUMENT_CANONICALISATION

DATACITE_DOI = "10.15497/rda00157"
CROSSREF_DOI = "10.1038/sdata.2016.18"
ORCID_ID = "0000-0002-1825-0097"
ROR_ID = "02b5d8509"
BROKEN = "10.1000/broken"
# DOIs whose records name other kinds of work: DOI -> (agency, its type for the work).
TYPED = {
    "10.5281/zenodo.1": ("DataCite", "Software"),
    "10.5281/zenodo.2": ("DataCite", "Dataset"),
    "10.5281/zenodo.3": ("DataCite", "DataPaper"),
    "10.13039/grant.4": ("Crossref", "grant"),
    "10.1016/article.5": ("Crossref", "journal-article"),
}
ALL = ["datacite", "crossref", "orcid", "ror"]
ID_FIELD = {"datacite": "doi", "crossref": "doi", "orcid": "orcid", "ror": "id"}

# Path on each registry's API -> its answer, cut to the fields the server reads.
ANSWERS: dict[str, dict[str, Any]] = {
    f"/dois/{DATACITE_DOI}": {
        "data": {
            "attributes": {
                "doi": DATACITE_DOI,
                "titles": [{"title": "Data Director Agentic AI Tool Blueprint"}],
                "types": {"resourceTypeGeneral": "Other"},
                "publisher": "Research Data Alliance",
                "publicationYear": 2026,
            }
        }
    },
    f"/works/{CROSSREF_DOI}": {
        "message": {
            "DOI": CROSSREF_DOI,
            "title": ["The FAIR Guiding Principles for scientific data management and stewardship"],
            "type": "journal-article",
        }
    },
    f"/v3.0/{ORCID_ID}/person": {
        "name": {"given-names": {"value": "Josiah"}, "family-name": {"value": "Carberry"}}
    },
    f"/v2/organizations/{ROR_ID}": {
        "id": f"https://ror.org/{ROR_ID}",
        "names": [
            {"value": "NERC", "types": ["acronym"]},
            {"value": "Natural Environment Research Council", "types": ["ror_display", "label"]},
        ],
        "types": ["funder", "government"],
        "status": "active",
        "external_ids": [{"type": "fundref", "all": ["501100000270"], "preferred": "501100000270"}],
    },
}
for _doi, (_agency, _type) in TYPED.items():
    if _agency == "DataCite":
        ANSWERS[f"/dois/{_doi}"] = {
            "data": {"attributes": {"doi": _doi, "types": {"resourceTypeGeneral": _type}}}
        }
    else:
        ANSWERS[f"/works/{_doi}"] = {"message": {"DOI": _doi, "type": _type}}


def answer(req: httpx.Request) -> httpx.Response:
    if req.url.path.endswith(BROKEN):
        return httpx.Response(500)
    found = ANSWERS.get(req.url.path)
    return httpx.Response(200, json=found) if found is not None else httpx.Response(404)


def registries() -> dict[str, Registry]:
    def http(name: str) -> Http:
        return Http(name, transport=httpx.MockTransport(answer), pauses=())

    return {
        "datacite": doi_registry("DataCite", DataCite(http("DataCite"))),
        "crossref": doi_registry("Crossref", Crossref(http("Crossref"))),
        "orcid": orcid_registry(Orcid(http("ORCID"))),
        "ror": ror_registry(RorSources(index=None, api=RorApi(http("ROR")))),
    }


def tool_server(registry: Registry) -> ToolServer:
    listed = [t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in registry.tools]
    return ToolServer(
        name=registry.name,
        url=f"http://127.0.0.1:8310/{registry.name}/mcp",
        id_field=ID_FIELD[registry.name],
        canonicalisation=DOCUMENT_CANONICALISATION,
        tools_sha256=tools_digest(listed),
    )


def run(tmp_path: Path, identifiers: list[str], granted: list[str] = ALL) -> Envelope:
    served = registries()
    serve: Callable[[ToolServer], Any] = lambda s: mcp_server(served[s.name])  # noqa: E731
    conductor = make_conductor(
        tmp_path / "runs",
        LinkingAdviser(),
        profile=tools_profile(tmp_path, {"advisor.linking": granted}),
        gateway=fake_gateway(*(tool_server(r) for r in served.values()), serve=serve),
    )
    env = conductor.invoke(
        request("advisor.linking", LinkCandidates(identifiers=identifiers)),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert conductor.grounding_reports[env.invocation_id].passed
    return env


def test_a_datacite_doi_carries_its_record_and_cites_it(tmp_path: Path) -> None:
    env = run(tmp_path, ["10.15497/RDA00157", f"https://doi.org/{DATACITE_DOI}"])
    payload = env.payload_as(RelatedIdentifiers)
    for link in payload.links:
        assert link.resolved is True
        assert link.title == "Data Director Agentic AI Tool Blueprint"
        assert link.resource_type == "Other"
        assert link.message.startswith("Found through DataCite")
    # Both spellings name one record: it is cited once, as the conductor recorded it.
    assert [r.source_id for r in env.tool_retrievals] == [f"tool:datacite/{DATACITE_DOI}"] * 2
    assert [g.source_id for g in payload.grounded_on] == [f"tool:datacite/{DATACITE_DOI}"]
    assert [e.source_id for e in env.evidence] == [f"tool:datacite/{DATACITE_DOI}"]


def test_a_doi_datacite_does_not_hold_is_found_through_crossref(tmp_path: Path) -> None:
    env = run(tmp_path, [CROSSREF_DOI])
    [link] = env.payload_as(RelatedIdentifiers).links
    assert link.resolved is True
    assert link.resource_type == "journal-article"
    assert link.message.startswith("Found through Crossref")
    assert [(r.tool_server, r.source_id) for r in env.tool_retrievals] == [
        ("crossref", f"tool:crossref/{CROSSREF_DOI}")
    ]


def test_an_orcid_id_and_a_ror_id_resolve_to_who_and_what_they_name(tmp_path: Path) -> None:
    env = run(tmp_path, [ORCID_ID, f"https://ror.org/{ROR_ID}"])
    person, organisation = env.payload_as(RelatedIdentifiers).links
    assert (person.resolved, person.title, person.resource_type) == (
        True,
        "Josiah Carberry",
        "Person",
    )
    assert (organisation.resolved, organisation.title, organisation.resource_type) == (
        True,
        "Natural Environment Research Council",
        "funder",
    )
    assert sorted(r.source_id for r in env.tool_retrievals) == [
        f"tool:orcid/https://orcid.org/{ORCID_ID}",
        f"tool:ror/https://ror.org/{ROR_ID}",
    ]


def test_a_doi_neither_agency_holds_is_not_found(tmp_path: Path) -> None:
    env = run(tmp_path, ["10.1234/unknown", DATACITE_DOI])
    missing, found = env.payload_as(RelatedIdentifiers).links
    assert missing.resolved is False and missing.valid and missing.title is None
    assert missing.message.startswith("Not found by DataCite or Crossref")
    assert found.resolved is True


def test_a_lookup_that_fails_everywhere_is_recorded_by_form_only(tmp_path: Path) -> None:
    env = run(tmp_path, [BROKEN])
    [link] = env.payload_as(RelatedIdentifiers).links
    assert link.resolved is False
    assert link.message.startswith("Could not be looked up through DataCite and Crossref")


def test_grant_numbers_and_malformed_ids_are_not_looked_up(tmp_path: Path) -> None:
    env = run(tmp_path, ["EP/T012345/1", "0000-0002-1825-0098", DATACITE_DOI])
    links = env.payload_as(RelatedIdentifiers).links
    assert [link.resolved for link in links] == [None, None, True]
    assert [r.tool_server for r in env.tool_retrievals] == ["datacite"]


@pytest.mark.parametrize(
    ("granted", "resolved", "form_only"),
    [
        (["crossref"], "DOIs were looked up", "ORCID iDs and ROR ids were checked by form only"),
        ([], None, "DOIs, ORCID iDs and ROR ids were checked by form only"),
    ],
)
def test_the_limitations_say_which_schemes_were_looked_up(
    tmp_path: Path, granted: list[str], resolved: str | None, form_only: str
) -> None:
    env = run(tmp_path, [CROSSREF_DOI, ORCID_ID], granted=granted)
    payload = env.payload_as(RelatedIdentifiers)
    assert any(lim.startswith(form_only) for lim in payload.limitations)
    looked_up = [lim for lim in payload.limitations if "were looked up" in lim]
    assert [lim.startswith(resolved or "") for lim in looked_up] == ([True] if resolved else [])
    assert payload.links[1].resolved is None
    if not granted:
        assert env.tool_retrievals == []


@pytest.mark.parametrize(
    ("doi", "relation"),
    [
        ("10.5281/zenodo.1", "References"),
        ("10.5281/zenodo.2", "References"),
        ("10.5281/zenodo.3", "IsDescribedBy"),
        ("10.1016/article.5", "IsSupplementTo"),
        ("10.13039/grant.4", None),
    ],
)
def test_a_resolved_doi_is_given_the_relation_its_type_of_work_suits(
    tmp_path: Path, doi: str, relation: str | None
) -> None:
    env = run(tmp_path, [doi])
    [link] = env.payload_as(RelatedIdentifiers).links
    assert link.resolved is True
    assert link.resource_type == TYPED[doi][1]
    assert link.relation == relation


def test_a_doi_not_resolved_or_of_an_unknown_type_keeps_the_default_relation(
    tmp_path: Path,
) -> None:
    default = next(s.relation for s in load_schemes() if s.name == "doi")
    env = run(tmp_path, ["10.1234/unknown", BROKEN, DATACITE_DOI])
    missing, failed, other = env.payload_as(RelatedIdentifiers).links
    assert (missing.resolved, failed.resolved, other.resolved) == (False, False, True)
    assert other.resource_type == "Other"
    assert [missing.relation, failed.relation, other.relation] == [default] * 3


def test_a_funding_organisation_is_offered_its_crossref_funder_id(tmp_path: Path) -> None:
    env = run(tmp_path, [ROR_ID])
    [link] = env.payload_as(RelatedIdentifiers).links
    assert link.resolved is True and link.relation is None
    assert "https://doi.org/10.13039/501100000270" in link.message

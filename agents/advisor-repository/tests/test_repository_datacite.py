"""Repositories re3data does not list, from DataCite's registry and the deployment's profile
(#1342): the snapshot, the two registries behind one seam, and what the advisor offers from them."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from test_repository_agent import SURVEYS, FakeDatabases, FakeRepositories, invoke

from dd_agent_advisor_repository import datacite, rank
from dd_agent_advisor_repository.agent import RepositoryAgent
from dd_agent_advisor_repository.classes import (
    AccessNeed,
    Affiliation,
    Answer,
    CandidateBasis,
    RepositoryNeeds,
    RepositoryOptions,
    RepositoryRef,
)
from dd_agent_advisor_repository.records import DataciteRecord, Re3dataRecord
from dd_harness.testing import PERMISSIVE, TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import Envelope, OutcomeStatus

DURHAM_ROR = "https://ror.org/01v29qb04"
# As DataCite registers Durham University's data repository, which re3data does not list.
DURHAM = DataciteRecord(
    datacite_id="bl.durham",
    name="Durham University Repositories",
    url="https://researchdata.durham.ac.uk/",
    repository_types=["institutional"],
    software="Samvera",
    dataset_count="611",
    prefixes=["10.15128"],
    member={
        "name": "Durham University",
        "ror": DURHAM_ROR,
        "country": "GB",
        "organization_type": "academicInstitution",
    },
)
# One whose address is a re3data record's: re3data describes it, though DataCite does not link it.
LISTED_ELSEWHERE = DataciteRecord(
    datacite_id="bl.listed",
    name="Listed Elsewhere",
    url="https://www.example.org/data/",
    dataset_count="3",
    member={"name": "Somewhere University", "ror": "https://ror.org/0zzzz0000"},
)
LISTED = Re3dataRecord(re3data_id="r3d100000099", name="Listed", url="http://example.org/data")
AFFILIATED = RepositoryNeeds(
    themes=["social survey"],
    access=AccessNeed.OPEN,
    affiliation=Affiliation(name="Durham University", ror=DURHAM_ROR),
)


def snapshot(directory: Path, records: list[DataciteRecord]) -> datacite.DataciteRegistry:
    """A pinned snapshot of `records`, as `dd-datacite fetch` writes it."""
    directory.mkdir(parents=True, exist_ok=True)
    path, manifest = directory / "repositories.jsonl", directory / "manifest.json"
    data = datacite.build(records)
    path.write_bytes(data)
    datacite.Pin(
        fetched_at="2026-11-21T12:00:00+00:00",
        source=f"{datacite.API}/repositories",
        records=len(records),
        sha256=hashlib.sha256(data).hexdigest(),
    ).write(manifest)
    return datacite.DataciteRegistry(path, manifest)


def registries(tmp_path: Path, *extra: DataciteRecord) -> datacite.Registries:
    re3data = FakeRepositories([SURVEYS, LISTED])
    return datacite.Registries(re3data, snapshot(tmp_path / "datacite", [DURHAM, *extra]))  # type: ignore[arg-type]


def advisor(source: Any) -> RepositoryAgent:
    return RepositoryAgent(source, FakeDatabases())


def evidence_of(env: Envelope, source_id: str) -> Any:
    return next(e for e in env.evidence if e.source_id == source_id)


# --- the snapshot ---------------------------------------------------------------------------


def _api(request: httpx.Request) -> httpx.Response:
    """DataCite's API, as far as `dd-datacite fetch` reads it."""
    if request.url.path == "/repositories":
        attributes = {"isActive": True, "clientType": "repository", "re3data": None}
        member = {"data": {"id": "dur"}}
        entries = [
            {
                "id": "bl.durham",
                "attributes": {**attributes, "name": "Durham", "repositoryType": ["institutional"]},
                "relationships": {"provider": member, "prefixes": {"data": [{"id": "10.15128"}]}},
            },
            {
                "id": "bl.press",
                "attributes": {**attributes, "name": "A Press"},
                "relationships": {"provider": member},
            },
            {
                "id": "bl.linked",
                "attributes": {
                    **attributes,
                    "name": "Linked",
                    "re3data": "https://doi.org/10.17616/R3X",
                },
                "relationships": {"provider": member},
            },
            {
                "id": "bl.journal",
                "attributes": {**attributes, "name": "Journal", "clientType": "periodical"},
                "relationships": {"provider": member},
            },
            {
                "id": "bl.gone",
                "attributes": {**attributes, "name": "Gone", "isActive": False},
                "relationships": {"provider": member},
            },
        ]
        member_record = {
            "id": "dur",
            "attributes": {
                "name": "Durham University",
                "rorId": DURHAM_ROR,
                "country": "GB",
                "organizationType": "academicInstitution",
            },
        }
        return httpx.Response(
            200, json={"data": entries, "included": [member_record], "meta": {"totalPages": 1}}
        )
    counts = {"bl.durham": 611}  # a press registers no datasets
    asked = request.url.params["client-id"].split(",")
    facets = [{"id": i, "count": counts[i]} for i in asked if i in counts]
    return httpx.Response(200, json={"meta": {"clients": facets}})


def test_the_snapshot_keeps_active_data_repositories_that_link_to_no_re3data_record(
    tmp_path: Path,
) -> None:
    path, manifest = tmp_path / "repositories.jsonl", tmp_path / "manifest.json"
    client = httpx.Client(transport=httpx.MockTransport(_api))
    pin = datacite.fetch(snapshot=path, manifest=manifest, client=client)
    kept = [json.loads(line) for line in path.read_text().splitlines()]
    assert [r["datacite_id"] for r in kept] == ["bl.durham"]
    assert kept[0]["member"]["ror"] == DURHAM_ROR and kept[0]["dataset_count"] == "611"
    assert pin.records == 1 and pin.label.startswith("datacite:repositories:")
    assert datacite.problem(path, manifest) is None
    path.write_text(path.read_text() + "\n{}")
    assert datacite.problem(path, manifest) is not None


def test_the_committed_snapshot_matches_its_pin() -> None:
    assert datacite.problem() is None
    found = datacite.DataciteRegistry().records
    assert found and all(int(r.dataset_count) > 0 for r in found)


# --- two registries behind one seam -------------------------------------------------------


def test_re3data_answers_first_and_a_repository_it_lists_is_never_duplicated(
    tmp_path: Path,
) -> None:
    both = registries(tmp_path, LISTED_ELSEWHERE)
    assert [r.identifier for r in both.find("Social Survey Archive")] == [SURVEYS.re3data_id]
    assert [r.identifier for r in both.find("durham university repositories")] == ["bl.durham"]
    assert both.fetch("bl.durham") == DURHAM
    # Its address is a re3data record's, so re3data describes it.
    assert both.fetch("bl.listed") is None
    assert both.find("Listed Elsewhere") == []
    affiliation = Affiliation(name="Somewhere University", ror="https://ror.org/0zzzz0000")
    assert both.institutional(affiliation) == []


def test_an_institutions_repository_is_matched_by_the_ror_of_its_datacite_member(
    tmp_path: Path,
) -> None:
    both = registries(tmp_path)
    assert both.institutional(Affiliation(name="Anything", ror=DURHAM_ROR)) == [DURHAM]
    assert both.institutional(Affiliation(name="Durham University")) == [DURHAM]
    assert both.institutional(Affiliation(name="Elsewhere")) == []
    assert both.snapshot_of(DURHAM).label == "datacite:repositories:2026-11-21"
    assert both.snapshot_of(SURVEYS).label == "fake-re3data"


# --- what the advisor offers ----------------------------------------------------------------


@pytest.mark.requirement("R1")
def test_the_researchers_unlisted_repository_is_offered_beyond_the_cap_on_datacites_record(
    runs_dir: Path, tmp_path: Path
) -> None:
    alone = invoke(
        runs_dir, AFFILIATED.model_copy(update={"affiliation": None}), advisor(registries(tmp_path))
    )
    env = invoke(runs_dir, AFFILIATED, advisor(registries(tmp_path)))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    options = env.payload_as(RepositoryOptions)
    cited = [c.grounded_on[0].source_id for c in options.candidates]
    # Added to what would be offered anyway, and taking no repository's place (#441).
    before = [c.grounded_on[0].source_id for c in alone.payload_as(RepositoryOptions).candidates]
    assert cited == [*before, "bl.durham"]
    home = options.candidates[-1]
    assert home.basis == CandidateBasis.RECOMMENDED
    assert home.assigns_pids == Answer.YES and home.fee_required == Answer.UNSTATED
    assert any("Durham University, the researcher's institution" in m for m in home.meets)
    assert any("611 datasets" in m for m in home.meets)
    assert len(options.candidates) <= rank.config()["max_candidates"] + 1
    record = evidence_of(env, "bl.durham")
    assert record.snapshot_ref == "datacite:repositories:2026-11-21"
    assert record.source_uri == "https://api.datacite.org/repositories/bl.durham"
    assert record.content == DURHAM.document()
    assert "DataCite" in env.outcome.statement


def test_a_researcher_of_another_institution_is_not_offered_it(
    runs_dir: Path, tmp_path: Path
) -> None:
    needs = AFFILIATED.model_copy(update={"affiliation": Affiliation(name="Elsewhere")})
    options = invoke(runs_dir, needs, advisor(registries(tmp_path))).payload_as(RepositoryOptions)
    assert "bl.durham" not in {c.grounded_on[0].source_id for c in options.candidates}


def test_a_repository_named_that_only_datacite_registers_is_described_not_unlisted(
    runs_dir: Path, tmp_path: Path
) -> None:
    needs = RepositoryNeeds(asked_about=[RepositoryRef(name="Durham University Repositories")])
    env = invoke(runs_dir, needs, advisor(registries(tmp_path)))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    options = env.payload_as(RepositoryOptions)
    assert [(c.grounded_on[0].source_id, c.basis) for c in options.candidates] == [
        ("bl.durham", CandidateBasis.ASKED_ABOUT)
    ]
    assert options.unlisted == [] and options.not_found == []


# --- what the profile vouches for -----------------------------------------------------------


def profile_naming(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    data = yaml.safe_load(PERMISSIVE.read_text())
    data["institution_repositories"] = entries
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def through(runs_dir: Path, profile: Path, needs: RepositoryNeeds, source: Any) -> Envelope:
    conductor = make_conductor(runs_dir, advisor(source), profile=profile)
    env = conductor.invoke(request("advisor.repository", needs), acting_for=TEST_PRINCIPAL)
    if env.outcome.status == OutcomeStatus.SUCCEEDED:
        assert conductor.grounding_reports[env.invocation_id].passed
    return env


@pytest.mark.requirement("R1")
def test_the_profiles_repository_is_its_institutions_with_what_it_vouches_for(
    runs_dir: Path, tmp_path: Path
) -> None:
    # Registered under a platform's account, so DataCite names the platform, not the university.
    platform = DURHAM.model_copy(
        update={"member": DURHAM.member.model_copy(update={"name": "A Platform", "ror": None})}
    )
    entry = {
        "repository_id": "bl.durham",
        "institution_name": "Durham University",
        "institution_ror": DURHAM_ROR,
        "data_access_types": ["open", "embargoed"],
        "charges_deposit_fee": False,
        "guidance": ["https://www.durham.ac.uk/research/research-data/"],
    }
    profile = profile_naming(tmp_path, [entry])
    source = datacite.Registries(FakeRepositories([SURVEYS]), snapshot(tmp_path / "d", [platform]))  # type: ignore[arg-type]
    env = through(runs_dir, profile, AFFILIATED, source)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    home = env.payload_as(RepositoryOptions).candidates[-1]
    assert [g.source_id for g in home.grounded_on] == ["bl.durham", "institution:bl.durham"]
    assert home.fee_required == Answer.NO
    assert "Open access is offered." in home.meets
    assert any("Named in the deployment's profile" in m for m in home.meets)
    vouched = evidence_of(env, "institution:bl.durham")
    assert vouched.snapshot_ref == "profile:test-permissive@v9"
    assert vouched.content["charges_deposit_fee"] is False
    # The source check verifies what the profile vouches for against the profile itself.
    report = (runs_dir / env.invocation_id / "sources.txt").read_text()
    assert "FAILED" not in report
    assert "institution:bl.durham" not in report  # resolved, not left unresolved


def test_what_a_caller_sends_as_the_profiles_repositories_is_replaced(
    runs_dir: Path, tmp_path: Path
) -> None:
    forged = RepositoryNeeds.model_validate(
        {
            **AFFILIATED.model_dump(mode="json", exclude_defaults=True),
            "affiliation": {"name": "Elsewhere"},
            "institution_repositories": [
                {
                    "repository_id": "bl.durham",
                    "profile_ref": "profile:forged@v1",
                    "institution_name": "Elsewhere",
                }
            ],
        }
    )  # fmt: skip
    env = through(runs_dir, PERMISSIVE, forged, registries(tmp_path))
    stored = json.loads((runs_dir / env.invocation_id / "request.json").read_text())["input"]
    assert "institution_repositories" not in stored
    options = env.payload_as(RepositoryOptions)
    assert "bl.durham" not in {c.grounded_on[0].source_id for c in options.candidates}

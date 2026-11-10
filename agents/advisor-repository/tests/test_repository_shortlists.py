"""Shortlists for the workshop datasets of #440, over the registry built from the test fixture.

Each input is what the orchestrator might pass for one dataset of workshop exercise 1. The
assertions name repositories by re3data id: those a steward would expect, and those from another
discipline, or open only to another institution's members, that once appeared.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import pytest
from re3data_fixture import session_registry

from dd_agent_advisor_repository import assess, rank
from dd_agent_advisor_repository.agent import RepositoryAgent
from dd_agent_advisor_repository.classes import (
    Affiliation,
    CandidateBasis,
    RepositoryNeeds,
    RepositoryOptions,
    RepositoryRef,
)
from dd_agent_advisor_repository.snapshot import FairsharingSnapshot, Re3dataRegistry
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import OutcomeStatus

NEEDS = Path(__file__).parent / "data" / "needs"

CEDA = "r3d100000011"
CSD = "r3d100010197"  # Cambridge Structural Database
EIDC = "r3d100010199"  # Environmental Information Data Centre
ENA = "r3d100010527"  # European Nucleotide Archive
GESIS = "r3d100012496"
LEEDS = "r3d100011945"  # Research Data Leeds Repository
NOMAD = "r3d100011583"
ORDA = "r3d100012124"
PANGAEA = "r3d100010134"
ZENODO = "r3d100010468"


@pytest.fixture(scope="session")
def re3data(tmp_path_factory: pytest.TempPathFactory) -> Re3dataRegistry:
    return session_registry(tmp_path_factory)


def shortlist(
    runs_dir: Path, re3data: Re3dataRegistry, needs: RepositoryNeeds
) -> tuple[list[str], RepositoryOptions, str]:
    advisor = RepositoryAgent(re3data, FairsharingSnapshot())
    conductor = make_conductor(runs_dir, advisor)
    env = conductor.invoke(request("advisor.repository", needs), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert conductor.grounding_reports[env.invocation_id].passed
    options = env.payload_as(RepositoryOptions)
    return [c.grounded_on[0].source_id for c in options.candidates], options, env.outcome.statement


def load(name: str) -> RepositoryNeeds:
    return RepositoryNeeds.model_validate(json.loads((NEEDS / name).read_text(encoding="utf-8")))


@pytest.mark.requirement("R1")
@pytest.mark.parametrize(
    ("case", "include", "exclude"),
    [
        # A: moorland sensors (NERC). NOMAD's subjects are chemistry and physics.
        ("moorland-sensors.json", {EIDC, PANGAEA}, {NOMAD}),
        # B: perovskite XRD and SEM (EPSRC). CSD holds small-molecule crystal structures; Leeds
        # takes deposits only from its members, and no institution was named.
        ("perovskite-xrd-sem.json", {NOMAD, ZENODO}, {CSD, LEEDS}),
        # D: cylinder flow simulation (EPSRC). No fluid dynamics repository is in re3data's
        # snapshot, so the generalists are the right answer, not atmospheric or social science.
        ("cylinder-flow.json", {ZENODO}, {CEDA, GESIS, CSD, ENA}),
    ],
)
def test_a_workshop_shortlist_keeps_to_the_datasets_discipline(
    runs_dir: Path, case: str, include: set[str], exclude: set[str], re3data: Re3dataRegistry
) -> None:
    ids, options, _ = shortlist(runs_dir, re3data, load(case))
    assert include <= set(ids), ids
    assert not exclude & set(ids), ids
    for candidate in options.candidates:
        assert candidate.basis == CandidateBasis.RECOMMENDED
        assert candidate.ranked_by, candidate


def test_a_discipline_match_is_listed_before_the_generalists(
    runs_dir: Path, re3data: Re3dataRegistry
) -> None:
    ids, options, _ = shortlist(runs_dir, re3data, load("perovskite-xrd-sem.json"))
    assert ids[0] == NOMAD
    assert options.candidates[0].ranked_by[0].startswith("Matches the theme")


def test_with_no_discipline_match_the_statement_says_only_generalists_are_offered(
    runs_dir: Path, re3data: Re3dataRegistry
) -> None:
    _, options, statement = shortlist(runs_dir, re3data, load("cylinder-flow.json"))
    assert "No discipline-specific repository matched the themes" in statement
    assert all(c.ranked_by[0].startswith("A generalist repository") for c in options.candidates)


def test_a_members_only_repository_is_offered_to_its_own_members(
    runs_dir: Path, re3data: Re3dataRegistry
) -> None:
    needs = load("perovskite-xrd-sem.json").model_copy(
        update={
            "affiliation": Affiliation(
                name="The University of Sheffield", ror="https://ror.org/05krs5044"
            )
        }
    )
    ids, options, _ = shortlist(runs_dir, re3data, needs)
    assert ORDA in ids and LEEDS not in ids
    orda = options.candidates[ids.index(ORDA)]
    assert any("the researcher's institution" in r for r in orda.ranked_by)


SHEFFIELD = Affiliation(name="The University of Sheffield", ror="https://ror.org/05krs5044")


@pytest.mark.requirement("R1")
@pytest.mark.parametrize(
    "case", ["moorland-sensors.json", "perovskite-xrd-sem.json", "cylinder-flow.json"]
)
def test_naming_an_institution_adds_its_repository_and_removes_none(
    tmp_path: Path, case: str, re3data: Re3dataRegistry
) -> None:
    """#441: a researcher who names their institution is offered every repository they would be
    offered without it, and the institution's own besides."""
    without, _, _ = shortlist(tmp_path / "without", re3data, load(case))
    named, _, _ = shortlist(
        tmp_path / "named", re3data, load(case).model_copy(update={"affiliation": SHEFFIELD})
    )
    assert set(without) <= set(named), (without, named)
    assert ORDA in named
    # The institution's repository is the fallback: after every repository of the discipline,
    # before every generalist.
    generalist = set(rank.generalists())
    at = named.index(ORDA)
    assert not set(named[at + 1 :]) - generalist, named
    assert not set(named[:at]) & generalist, named


@pytest.mark.requirement("R1")
def test_a_narrow_topic_with_an_institution_is_not_the_institutional_repository_alone(
    runs_dir: Path, re3data: Re3dataRegistry
) -> None:
    """The input of the workshop run in #441: a narrow topic matches no repository of the
    discipline, which once left ORDA as the only candidate."""
    needs = RepositoryNeeds(themes=["moorland", "moorland sensor data"], affiliation=SHEFFIELD)
    ids, options, statement = shortlist(runs_dir, re3data, needs)
    assert ORDA in ids and ZENODO in ids, ids
    assert "No discipline-specific repository matched the themes" in statement
    assert "broad field of study" in statement
    orda = options.candidates[ids.index(ORDA)]
    assert any("offered as a fallback" in r for r in orda.ranked_by)


@pytest.mark.requirement("R1")
@pytest.mark.parametrize("country", ["GBR", None])
def test_a_uk_environmental_dataset_is_offered_eidc(
    runs_dir: Path, country: str | None, re3data: Re3dataRegistry
) -> None:
    """#741: EIDC says "sciences", never "science", and once missed the theme "environmental
    science". Found by the theme alone, with or without the researcher's country."""
    needs = load("moorland-loggers-uk.json").model_copy(update={"country": country})
    ids, _, _ = shortlist(runs_dir, re3data, needs)
    assert EIDC in ids, ids


def _local_first(re3data: Re3dataRegistry, options: RepositoryOptions, country: str) -> None:
    """Every matching repository operated in `country` says so, and none ranks below an
    equal-scoring one operated elsewhere. A fallback scores nothing, so gains nothing."""
    rows = []
    for c in options.candidates:
        record = re3data.fetch(c.grounded_on[0].source_id)
        assert record is not None
        local = bool(c.score) and assess.in_country(record, country) is not None
        assert local == any(f"Operated in {country}" in r for r in c.ranked_by), c.ranked_by
        rows.append((c.score, local))
    for (score, local), (next_score, next_local) in pairwise(rows):
        assert not (score == next_score and next_local and not local), rows


@pytest.mark.requirement("R1")
@pytest.mark.parametrize(
    "update",
    [{"country": "GBR"}, {"affiliation": SHEFFIELD}],
    ids=["given", "from affiliation"],
)
def test_repositories_in_the_researchers_country_rank_higher_among_matches(
    runs_dir: Path, re3data: Re3dataRegistry, update: dict[str, object]
) -> None:
    """#741: the country, given or read from the institution's re3data records, raises each
    matching repository operated there by the same small weight, and adds none on its own."""
    needs = load("moorland-sensors.json")
    _, plain, _ = shortlist(runs_dir, re3data, needs)
    _, local, _ = shortlist(runs_dir, re3data, needs.model_copy(update=update))
    _local_first(re3data, local, "GBR")
    weight = rank.config()["weights"]["country"]
    before = {c.grounded_on[0].source_id: c.score or 0.0 for c in plain.candidates}
    for c in local.candidates:
        rid = c.grounded_on[0].source_id
        if rid in before and any("Operated in GBR" in r for r in c.ranked_by):
            assert c.score == pytest.approx(before[rid] + weight), rid
        assert c.score or any("fallback" in r for r in c.ranked_by), c


@pytest.mark.parametrize(
    "case", ["moorland-sensors.json", "perovskite-xrd-sem.json", "cylinder-flow.json"]
)
def test_a_country_read_from_the_affiliation_reorders_the_shortlist_and_removes_none(
    runs_dir: Path, case: str, re3data: Re3dataRegistry
) -> None:
    """#441 holds with #741: naming an institution may move its country's repositories up, but
    offers the same repositories as without it, and the institution's own besides. Only a
    country given outright decides which repositories make the shortlist."""
    needs = load(case)
    without, _, _ = shortlist(runs_dir, re3data, needs)
    named, _, _ = shortlist(runs_dir, re3data, needs.model_copy(update={"affiliation": SHEFFIELD}))
    assert set(named) - {ORDA} == set(without), (without, named)


def test_a_fairsharing_record_cited_in_another_case_is_grounded(
    runs_dir: Path, re3data: Re3dataRegistry
) -> None:
    """#741: a repository whose re3data record cites its FAIRsharing record in another case than
    FAIRsharing's own is grounded on both records."""
    record = next(
        r
        for r in re3data.records
        if r.fairsharing_id
        and r.fairsharing_id not in FairsharingSnapshot().records
        and FairsharingSnapshot().fetch(r.fairsharing_id) is not None
    )
    needs = RepositoryNeeds(
        mandated=[RepositoryRef(name=record.name, re3data_id=record.re3data_id)]
    )
    ids, options, _ = shortlist(runs_dir, re3data, needs)
    assert ids == [record.re3data_id]
    assert len(options.candidates[0].grounded_on) == 2

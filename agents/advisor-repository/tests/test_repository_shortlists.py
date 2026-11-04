"""Shortlists for the workshop datasets of #440, over the committed re3data snapshot.

Each input is what the orchestrator might pass for one dataset of workshop exercise 1. The
assertions name repositories by re3data id: those a steward would expect, and those from another
discipline, or open only to another institution's members, that once appeared.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dd_agent_advisor_repository.agent import RepositoryAgent
from dd_agent_advisor_repository.classes import (
    Affiliation,
    CandidateBasis,
    RepositoryNeeds,
    RepositoryOptions,
)
from dd_agent_advisor_repository.snapshot import FairsharingSnapshot, Re3dataSnapshot
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


def shortlist(runs_dir: Path, needs: RepositoryNeeds) -> tuple[list[str], RepositoryOptions, str]:
    advisor = RepositoryAgent(Re3dataSnapshot(), FairsharingSnapshot())
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
        ("moorland-sensors.json", {EIDC, PANGAEA, CEDA}, {NOMAD}),
        # B: perovskite XRD and SEM (EPSRC). CSD holds small-molecule crystal structures; Leeds
        # takes deposits only from its members, and no institution was named.
        ("perovskite-xrd-sem.json", {NOMAD, ZENODO}, {CSD, LEEDS}),
        # D: cylinder flow simulation (EPSRC). No fluid dynamics repository is in re3data's
        # snapshot, so the generalists are the right answer, not atmospheric or social science.
        ("cylinder-flow.json", {ZENODO}, {CEDA, GESIS, CSD, ENA}),
    ],
)
def test_a_workshop_shortlist_keeps_to_the_datasets_discipline(
    runs_dir: Path, case: str, include: set[str], exclude: set[str]
) -> None:
    ids, options, _ = shortlist(runs_dir, load(case))
    assert include <= set(ids), ids
    assert not exclude & set(ids), ids
    for candidate in options.candidates:
        assert candidate.basis == CandidateBasis.RECOMMENDED
        assert candidate.ranked_by, candidate


def test_a_discipline_match_is_listed_before_the_generalists(runs_dir: Path) -> None:
    ids, options, _ = shortlist(runs_dir, load("perovskite-xrd-sem.json"))
    assert ids[0] == NOMAD
    assert options.candidates[0].ranked_by[0].startswith("Matches the theme")


def test_with_no_discipline_match_the_statement_says_only_generalists_are_offered(
    runs_dir: Path,
) -> None:
    _, options, statement = shortlist(runs_dir, load("cylinder-flow.json"))
    assert "No discipline-specific repository matched the themes" in statement
    assert all(c.ranked_by[0].startswith("A generalist repository") for c in options.candidates)


def test_a_members_only_repository_is_offered_to_its_own_members(runs_dir: Path) -> None:
    needs = load("perovskite-xrd-sem.json").model_copy(
        update={
            "affiliation": Affiliation(
                name="The University of Sheffield", ror="https://ror.org/05krs5044"
            )
        }
    )
    ids, options, _ = shortlist(runs_dir, needs)
    assert ORDA in ids and LEEDS not in ids
    orda = options.candidates[ids.index(ORDA)]
    assert any("the researcher's institution" in r for r in orda.ranked_by)


@pytest.mark.requirement("R1")
@pytest.mark.parametrize(
    ("affiliation", "home"),
    [
        (Affiliation(name="The University of Sheffield", ror="https://ror.org/05krs5044"), ORDA),
        (Affiliation(name="University of Leeds", ror="https://ror.org/024mrxd33"), LEEDS),
    ],
)
def test_naming_an_institution_adds_its_repository_without_narrowing_the_shortlist(
    runs_dir: Path, affiliation: Affiliation, home: str
) -> None:
    """#441: giving more information must not give a worse answer."""
    without, _, _ = shortlist(runs_dir, load("moorland-sensors.json"))
    needs = load("moorland-sensors.json").model_copy(update={"affiliation": affiliation})
    ids, options, _ = shortlist(runs_dir, needs)
    assert {EIDC, PANGAEA, CEDA} <= set(ids), ids
    assert set(without) <= set(ids)
    assert set(ids) - set(without) == {home}
    reasons = options.candidates[ids.index(home)].ranked_by
    assert any("institutional rather than a discipline fit" in r for r in reasons), reasons

"""What people in the project decided, read into the needs (`given.py`, docs/specs/projects.md
invariant 6): a decided required repository is mandated, and the repository the researcher chose
is described when nothing else is asked. The conductor fills both in a project; here they are
sent as a caller outside a project would, which the agent reads the same way."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_repository_agent import NEEDS, invoke

from dd_agent_advisor_repository.classes import (
    CandidateBasis,
    RepositoryNeeds,
    RepositoryOptions,
    RepositoryRef,
)
from dd_sdk.contract.facts import ChosenRepository, ProjectFact
from dd_sdk.contract.models import OutcomeStatus

pytestmark = pytest.mark.requirement("R1")

REQUIRED = ProjectFact(
    fact_kind="required_repository",
    fact_subject="required_repository",
    fact_repository_name="x",
    fact_re3data_id="r3d100000003",
)
CHOSEN = ChosenRepository(
    chosen_repository_name="x",
    chosen_repository_id="r3d100000003",
    chosen_re3data_id="r3d100000003",
)


def cited(options: RepositoryOptions) -> list[tuple[str, CandidateBasis]]:
    return [(c.grounded_on[0].source_id, c.basis) for c in options.candidates]


def test_a_decided_required_repository_is_mandated_whatever_the_caller_asked(
    runs_dir: Path,
) -> None:
    needs = NEEDS.model_copy(update={"project_decisions": [REQUIRED]})
    env = invoke(runs_dir, needs)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert cited(env.payload_as(RepositoryOptions)) == [("r3d100000003", CandidateBasis.MANDATED)]


def test_the_chosen_repository_is_described_when_nothing_else_is_asked(runs_dir: Path) -> None:
    env = invoke(runs_dir, RepositoryNeeds(project_repository=CHOSEN))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert cited(env.payload_as(RepositoryOptions)) == [("r3d100000003", CandidateBasis.CHOSEN)]


def test_a_caller_may_still_ask_for_a_shortlist_after_a_choice(runs_dir: Path) -> None:
    """A choice does not stop a researcher reconsidering: needs to search for still shortlist."""
    env = invoke(runs_dir, NEEDS.model_copy(update={"project_repository": CHOSEN}))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    bases = {basis for _, basis in cited(env.payload_as(RepositoryOptions))}
    assert bases == {CandidateBasis.RECOMMENDED}


def commitment(repository: str | None, subject: str = "survey responses") -> ProjectFact:
    """A sharing commitment of the data management plan, as the researcher confirmed it."""
    return ProjectFact(
        fact_kind="sharing_commitment",
        fact_subject=subject,
        commitment_repository=repository,
        commitment_quote="We will deposit the survey responses in the repository named.",
        commitment_document="0" * 64,
    )


def test_a_confirmed_plan_names_a_repository_described_beside_the_shortlist(
    runs_dir: Path,
) -> None:
    """#1233: the plan's repository is described, never mandated, and the shortlist stays."""
    needs = NEEDS.model_copy(update={"project_decisions": [commitment("Acme Data Cloud")]})
    env = invoke(runs_dir, needs)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    found = cited(env.payload_as(RepositoryOptions))
    assert found[0] == ("r3d100000003", CandidateBasis.IN_PLAN)
    assert {basis for _, basis in found[1:]} == {CandidateBasis.RECOMMENDED}
    assert "a plan's choice is not a mandate" in env.outcome.statement
    assert "data management plan" in env.payload_as(RepositoryOptions).candidates[0].rationale


def test_a_plan_repository_alone_is_described_without_a_shortlist(runs_dir: Path) -> None:
    env = invoke(runs_dir, RepositoryNeeds(project_decisions=[commitment("Acme Data Cloud")]))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert cited(env.payload_as(RepositoryOptions)) == [("r3d100000003", CandidateBasis.IN_PLAN)]


def test_a_plan_repository_that_is_also_required_is_mandated(runs_dir: Path) -> None:
    needs = RepositoryNeeds(project_decisions=[REQUIRED, commitment("Acme Data Cloud")])
    env = invoke(runs_dir, needs)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert cited(env.payload_as(RepositoryOptions)) == [("r3d100000003", CandidateBasis.MANDATED)]


def test_a_plan_repository_asked_about_too_is_described_once_as_the_plans(
    runs_dir: Path,
) -> None:
    needs = RepositoryNeeds(
        asked_about=[RepositoryRef(name="Acme Data Cloud")],
        project_decisions=[commitment("Acme Data Cloud")],
    )
    env = invoke(runs_dir, needs)
    assert cited(env.payload_as(RepositoryOptions)) == [("r3d100000003", CandidateBasis.IN_PLAN)]


def test_a_commitment_naming_no_repository_adds_nothing(runs_dir: Path) -> None:
    env = invoke(runs_dir, RepositoryNeeds(project_decisions=[commitment(None)]))
    assert env.outcome.status == OutcomeStatus.ABSTAINED


def test_the_chosen_repository_is_not_described_alone_beside_a_plan_repository(
    runs_dir: Path,
) -> None:
    needs = RepositoryNeeds(
        project_repository=CHOSEN.model_copy(
            update={"chosen_repository_name": "y", "chosen_re3data_id": "r3d100000001"}
        ),
        project_decisions=[commitment("Acme Data Cloud")],
    )
    env = invoke(runs_dir, needs)
    assert cited(env.payload_as(RepositoryOptions)) == [("r3d100000003", CandidateBasis.IN_PLAN)]


def test_an_unknown_plan_repository_is_not_found(runs_dir: Path) -> None:
    env = invoke(runs_dir, NEEDS.model_copy(update={"project_decisions": [commitment("Nowhere")]}))
    options = env.payload_as(RepositoryOptions)
    assert options.not_found == ["Nowhere"]
    assert CandidateBasis.IN_PLAN not in {c.basis for c in options.candidates}


def test_a_plan_repository_re3data_does_not_list_is_shown_as_the_plans(runs_dir: Path) -> None:
    """#1334: a repository re3data does not list, such as an institution's own, is still the
    researcher's option, shown as the plan's beside the shortlist."""
    env = invoke(runs_dir, NEEDS.model_copy(update={"project_decisions": [commitment("Nowhere")]}))
    options = env.payload_as(RepositoryOptions)
    assert [(u.name, u.basis) for u in options.unlisted] == [("Nowhere", CandidateBasis.IN_PLAN)]
    assert {c.basis for c in options.candidates} == {CandidateBasis.RECOMMENDED}


def test_each_repository_the_plan_names_for_one_output_is_the_plans(runs_dir: Path) -> None:
    """A plan that deposits an output in one repository and offers a copy to another gives a
    commitment for each (#1334)."""
    both = [commitment(r, f"survey responses ({r})") for r in ["Acme Data Cloud", "Nowhere"]]
    env = invoke(runs_dir, NEEDS.model_copy(update={"project_decisions": both}))
    options = env.payload_as(RepositoryOptions)
    assert cited(options)[0] == ("r3d100000003", CandidateBasis.IN_PLAN)
    assert [(u.name, u.basis) for u in options.unlisted] == [("Nowhere", CandidateBasis.IN_PLAN)]


def test_without_a_shortlist_unlisted_plan_repositories_are_named_in_the_abstention(
    runs_dir: Path,
) -> None:
    """A succeeded payload must rest on a record retrieved (docs/specs/grounding.md, G2), so with
    only unlisted repositories to show the advisor abstains, but names them rather than losing
    them."""
    env = invoke(runs_dir, RepositoryNeeds(project_decisions=[commitment("Nowhere")]))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert "Nowhere" in env.outcome.statement

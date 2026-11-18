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
CHOSEN = ChosenRepository(chosen_repository_name="x", chosen_re3data_id="r3d100000003")


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

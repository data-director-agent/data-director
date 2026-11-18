"""What people in the project decided, read into the context (`given.py`, docs/specs/projects.md
invariant 6): a decided licence is the mandated one, over what the caller sent, and a decision to
withhold or generalise a sensitive field says the data are sensitive where the caller did not say.
The conductor fills the decisions in a project; here they are sent as a caller outside a project
would, which the agent reads the same way."""

from __future__ import annotations

from pathlib import Path

from dd_agent_advisor_rights.agent import (
    SENSITIVE_FIRST,
    UNKNOWN_SENSITIVE_QUESTION,
    RightsAdviser,
)
from dd_agent_advisor_rights.classes import RightsContext, RightsOptions
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.facts import ProjectFact
from dd_sdk.contract.models import Envelope, OutcomeStatus

LICENCE = ProjectFact(fact_kind="licence", fact_subject="licence", licence_id="cc0-1.0")
WITHHELD = ProjectFact(
    fact_kind="sensitivity",
    fact_subject="participant_name",
    sensitive_subject="participant_name",
    sensitivity_decision="withhold",
)


def advise(runs_dir: Path, context: RightsContext) -> RightsOptions:
    env: Envelope = make_conductor(runs_dir, RightsAdviser()).invoke(
        request("advisor.rights", context), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    return env.payload_as(RightsOptions)


def test_a_decided_licence_is_mandated_over_the_callers(runs_dir: Path) -> None:
    payload = advise(
        runs_dir, RightsContext(mandated_licence="cc-by-4.0", project_decisions=[LICENCE])
    )
    assert [lic.spdx_id for lic in payload.licences] == ["CC0-1.0"]


def test_a_decision_to_withhold_says_the_data_are_sensitive(runs_dir: Path) -> None:
    payload = advise(runs_dir, RightsContext(reuse_wanted="any", project_decisions=[WITHHELD]))
    assert [a.level for a in payload.access_levels][: len(SENSITIVE_FIRST)] == list(SENSITIVE_FIRST)
    assert UNKNOWN_SENSITIVE_QUESTION not in [q.text for q in payload.questions]


def test_the_caller_saying_the_data_are_not_sensitive_stands(runs_dir: Path) -> None:
    """A decision on one field is not read over what the researcher said of the whole."""
    payload = advise(
        runs_dir,
        RightsContext(reuse_wanted="any", sensitive=False, project_decisions=[WITHHELD]),
    )
    assert payload.access_levels[0].level == "open"

"""advisor.fairness on the project's draft metadata record, at any point in the work (#430, #432):
what is met comes first, each of F, A, I and R is tallied, the next steps are ranked by rule, and
what the repository fills at deposit is neither counted nor recommended."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dd_agent_advisor_fairness.agent import FairAssessor
from dd_agent_advisor_fairness.classes import FairnessReport, FairPrinciple, ProjectMetadataDraft
from dd_agent_advisor_fairness.rules import load_checks
from dd_agent_advisor_fairness.testing import writer_reply
from dd_agent_advisor_fairness.write import ModelWriter
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import (
    ApprovedMetadataRecord,
    CurrentVersion,
    Derivation,
    DocumentVersionRef,
    Envelope,
    OutcomeStatus,
    ReasonCode,
    VersionState,
)
from dd_sdk.testing import FakeModel

DOCUMENT = "01900000-0000-7000-8000-00000000000a"
ORCID = "https://orcid.org/0000-0002-1825-0097"
# A draft as the Metadata Librarian writes it: what the researcher has not given yet is null.
DRAFT: dict[str, Any] = {
    "doi": None,
    "titles": [{"title": "Peat depth survey, 2025"}],
    "creators": [
        {"name": "Byron, Ada", "nameIdentifiers": [{"nameIdentifier": ORCID}]},
        {"name": "Babbage, Charles"},
    ],
    "subjects": None,
    "rightsList": [{"rights": "Creative Commons Attribution 4.0", "rightsIdentifier": "CC-BY-4.0"}],
    "formats": ["text/csv"],
    "relatedIdentifiers": None,
    "types": {"resourceTypeGeneral": "Dataset"},
}
# The version a person approved before the licence was given.
APPROVED: dict[str, Any] = {**DRAFT, "rightsList": None}
AFTER_DEPOSIT = {r.check for r in load_checks() if r.after_deposit}


def version(n: int, record: dict[str, Any], state: VersionState) -> CurrentVersion:
    return CurrentVersion(
        version_ref=DocumentVersionRef(document_id=DOCUMENT, version=n),
        media_type="application/json",
        document_text=json.dumps(record),
        version_state=state,
    )


def approved(n: int, record: dict[str, Any]) -> ApprovedMetadataRecord:
    return ApprovedMetadataRecord(
        version_ref=DocumentVersionRef(document_id=DOCUMENT, version=n),
        media_type="application/json",
        document_text=json.dumps(record),
    )


def assess(
    runs_dir: Path, given: ProjectMetadataDraft, assessor: FairAssessor | None = None
) -> Envelope:
    conductor = make_conductor(runs_dir, assessor or FairAssessor())
    env = conductor.invoke(request("advisor.fairness", given), acting_for=TEST_PRINCIPAL)
    if env.outcome.status == OutcomeStatus.SUCCEEDED:
        assert conductor.grounding_reports[env.invocation_id].passed
    return env


def report(runs_dir: Path, given: ProjectMetadataDraft) -> FairnessReport:
    env = assess(runs_dir, given)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    return env.payload_as(FairnessReport)


def in_project(record: dict[str, Any] = DRAFT, **more: Any) -> ProjectMetadataDraft:
    return ProjectMetadataDraft(
        project_metadata_draft=version(2, record, VersionState.PROPOSED), **more
    )


def test_what_a_draft_meets_comes_first_and_deposit_checks_last(runs_dir: Path) -> None:
    payload = report(runs_dir, in_project())
    states = [(c.met, bool(c.after_deposit)) for c in payload.checks]
    assert states == sorted(states, key=lambda s: (not s[0], s[1]))
    assert {c.check for c in payload.checks if c.after_deposit} == AFTER_DEPOSIT
    assert all(c.recommendation is None for c in payload.checks if c.after_deposit)
    assert all(c.recommendation for c in payload.checks if not c.met and not c.after_deposit)


def test_each_principle_is_tallied_without_the_deposit_checks(runs_dir: Path) -> None:
    payload = report(runs_dir, in_project())
    assert [t.principle_group for t in payload.principle_tallies] == list(FairPrinciple)
    counted = [c for c in payload.checks if not c.after_deposit]
    for tally in payload.principle_tallies:
        mine = [c for c in counted if c.principle.startswith(tally.principle_group.value)]
        assert tally.tally_assessed == len(mine)
        assert tally.tally_met == sum(c.met for c in mine)


def test_the_next_steps_are_the_highest_priority_checks_not_met(runs_dir: Path) -> None:
    payload = report(runs_dir, in_project())
    priority = {r.check: r.priority for r in load_checks()}
    to_act_on = sorted(
        (c.check for c in payload.checks if not c.met and not c.after_deposit),
        key=priority.__getitem__,
    )
    assert payload.next_steps == to_act_on[: len(payload.next_steps)]
    assert 1 <= len(payload.next_steps) <= 2


def test_what_is_newly_met_since_the_approved_version_is_marked(runs_dir: Path) -> None:
    payload = report(runs_dir, in_project(project_metadata_approved=approved(1, APPROVED)))
    newly = {c.check for c in payload.checks if c.newly_met}
    assert newly == {"licence-present", "licence-open"}
    assert payload.compared_with == DocumentVersionRef(document_id=DOCUMENT, version=1)
    assert payload.assessed_version == DocumentVersionRef(document_id=DOCUMENT, version=2)


def test_without_an_approved_version_nothing_is_compared(runs_dir: Path) -> None:
    payload = report(runs_dir, in_project())
    assert payload.compared_with is None
    assert all(c.newly_met is None for c in payload.checks)


def test_the_approved_version_itself_is_not_compared_with(runs_dir: Path) -> None:
    given = ProjectMetadataDraft(
        project_metadata_draft=version(1, DRAFT, VersionState.APPROVED),
        project_metadata_approved=approved(1, DRAFT),
    )
    payload = report(runs_dir, given)
    assert payload.compared_with is None


def test_outside_a_project_the_callers_text_is_assessed(runs_dir: Path) -> None:
    payload = report(runs_dir, ProjectMetadataDraft(draft_text=json.dumps(DRAFT)))
    assert payload.assessed_version is None
    assert any(c.met for c in payload.checks)


@pytest.mark.parametrize(
    "given",
    [
        ProjectMetadataDraft(),
        ProjectMetadataDraft(draft_text="title: not JSON"),
    ],
    ids=["no-draft", "not-datacite"],
)
def test_no_readable_draft_abstains(runs_dir: Path, given: ProjectMetadataDraft) -> None:
    env = assess(runs_dir, given)
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


def test_a_model_tailors_only_the_checks_to_act_on(runs_dir: Path) -> None:
    model = FakeModel(writer_reply(), model_id="claude-test")
    env = assess(runs_dir, in_project(), FairAssessor(ModelWriter(model)))
    payload = env.payload_as(FairnessReport)
    [sent] = model.sent
    body = json.loads(sent.messages[0]["content"])  # type: ignore[index]
    asked = {c["check"] for c in body["unmet_checks"]}
    assert asked == {c.check for c in payload.checks if not c.met and not c.after_deposit}
    assert all(
        c.recommendation_derivation == Derivation.TEMPLATE
        for c in payload.checks
        if c.recommendation
    )

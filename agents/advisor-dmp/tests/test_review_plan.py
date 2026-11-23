"""advisor.dmp reviews the plan a researcher attached (`setup.dmp-review`): a model reads it
against the core requirements, good practice and the decisions made in the project, and there is no
rule behind the review (docs/specs/agents.md, Model-backed personas)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dd_agent_advisor_dmp.agent import DmpChecker
from dd_agent_advisor_dmp.classes import DmpDiscrepancies, DmpReviewRequest, SectionFinding
from dd_agent_advisor_dmp.match import ModelMatcher
from dd_agent_advisor_dmp.read_plan import ModelReader
from dd_agent_advisor_dmp.review_model import REVIEW_PROMPT, ModelReviewer
from dd_dmp_template import SECTIONS
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.drafting import ApprovedPlan
from dd_sdk.contract.facts import FactKind, ProjectDocument, ProjectFact, SensitivityDecision
from dd_sdk.contract.models import (
    DocumentVersionRef,
    Envelope,
    GroundingMode,
    OutcomeStatus,
    ReasonCode,
)
from dd_sdk.model import declared
from dd_sdk.testing import FakeModel

PLANS = Path(__file__).parents[1] / "src" / "dd_agent_advisor_dmp" / "evals" / "data"
WRITTEN_ID = "01900000-0000-7000-8000-0000000000d1"
STORAGE = SECTIONS[2]
LEGAL = SECTIONS[3]


def attached(name: str) -> ProjectDocument:
    text = (PLANS / name).read_text(encoding="utf-8")
    return ProjectDocument(
        documentation_name=name,
        documentation_digest=hashlib.sha256(text.encode()).hexdigest(),
        documentation_media_type="text/markdown",
        documentation_size=len(text.encode()),
        documentation_added_at=datetime(2026, 11, 1, tzinfo=UTC),
        documentation_text=text,
    )


def run(runs_dir: Path, asked: DmpReviewRequest, agent: DmpChecker | None = None) -> Envelope:
    conductor = make_conductor(runs_dir, DmpChecker() if agent is None else agent)
    env = conductor.invoke(request("advisor.dmp", asked), acting_for=TEST_PRINCIPAL)
    if env.outcome.status == OutcomeStatus.SUCCEEDED:
        assert env.grounding_mode == GroundingMode.INPUT_ONLY
        assert conductor.grounding_reports[env.invocation_id].passed
    return env


def reviewer(model: FakeModel) -> DmpChecker:
    """Built as the factory builds it with a model."""
    agent = DmpChecker(ModelMatcher(model), ModelReader(model), ModelReviewer(model))
    agent.spec = replace(agent.spec, models=(declared(model),))
    return agent


def by_section(env: Envelope) -> dict[str, SectionFinding]:
    return {f.section: f for f in env.payload_as(DmpDiscrepancies).section_findings}


def readings(*items: tuple[str, str, str | None, str]) -> str:
    return json.dumps(
        {
            "readings": [
                {"requirement": r, "answered": a, "quote": q, "reason": why}
                for r, a, q, why in items
            ]
        }
    )


def review_of(*items: tuple[str, str, str | None, str]) -> FakeModel:
    return FakeModel(readings(*items))


def every_requirement(answered: str = "not") -> list[tuple[str, str, str | None, str]]:
    return [(s.id, answered, None, f"Nothing about {s.id}.") for s in SECTIONS]


COMPLETE = attached("complete.md")
BACKUP = "backed up nightly to a second site"


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_a_model_reads_the_plan_against_every_requirement(runs_dir: Path) -> None:
    items = [i for i in every_requirement() if i[0] != STORAGE.id]
    model = review_of(
        *items, (STORAGE.id, "partly", BACKUP, "It says nothing of security or who does it.")
    )
    env = run(runs_dir, DmpReviewRequest(project_documents=[COMPLETE]), reviewer(model))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    found = by_section(env)
    assert list(found) == [s.heading for s in SECTIONS]
    assert found[STORAGE.heading].finding == "vague"
    assert found[STORAGE.heading].quote == BACKUP
    assert found[LEGAL.heading].finding == "missing"
    assert found[LEGAL.heading].quote is None
    assert all(f.reason and f.message for f in found.values())
    payload = env.payload_as(DmpDiscrepancies)
    assert payload.limitations and not payload.discrepancies and not payload.dropped
    (sent,) = model.sent
    assert sent.system == REVIEW_PROMPT


def test_an_answer_that_is_full_is_covered(runs_dir: Path) -> None:
    model = review_of(
        (STORAGE.id, "fully", BACKUP, "Storage, backup and security are specific."),
        *[i for i in every_requirement() if i[0] != STORAGE.id],
    )
    env = run(runs_dir, DmpReviewRequest(project_documents=[COMPLETE]), reviewer(model))
    assert by_section(env)[STORAGE.heading].finding == "covered"


def test_the_model_is_given_the_requirements_the_decisions_and_the_plan(runs_dir: Path) -> None:
    decisions = [
        ProjectFact(fact_kind=FactKind.LICENCE, fact_subject="licence", licence_id="CC-BY-4.0"),
        ProjectFact(fact_kind=FactKind.FUNDER, fact_subject="f", fact_funder_name="NERC"),
        ProjectFact(
            fact_kind=FactKind.SENSITIVITY,
            fact_subject="nests",
            sensitive_subject="Nest locations",
            sensitivity_decision=SensitivityDecision.WITHHOLD,
        ),
    ]
    model = review_of(*every_requirement())
    asked = DmpReviewRequest(project_documents=[COMPLETE], project_decisions=decisions)
    run(runs_dir, asked, reviewer(model))
    (sent,) = model.sent
    content = json.dumps(sent.messages)
    for expected in (STORAGE.id, "CC-BY-4.0", "NERC", "Nest locations", "second site"):
        assert expected in content


def test_the_document_marked_as_the_plan_is_reviewed_rather_than_the_latest(
    runs_dir: Path,
) -> None:
    marked = attached("partial.md").model_copy(update={"documentation_is_plan": True})
    model = review_of(*every_requirement())
    asked = DmpReviewRequest(project_documents=[marked, COMPLETE])
    env = run(runs_dir, asked, reviewer(model))
    (sent,) = model.sent
    content = json.dumps(sent.messages)
    assert "Ethics and consent" in content and "second site" not in content
    assert "partial.md" in env.outcome.statement


def test_the_plan_written_in_the_project_is_reviewed_unless_one_attached_is_marked(
    runs_dir: Path,
) -> None:
    written = ApprovedPlan(
        version_ref=DocumentVersionRef(document_id=WRITTEN_ID, version=2),
        document_title="Peatland plan",
        media_type="text/markdown",
        document_text=(PLANS / "partial.md").read_text(encoding="utf-8"),
    )
    model = review_of(*every_requirement())
    env = run(
        runs_dir,
        DmpReviewRequest(project_documents=[COMPLETE], project_plan_approved=written),
        reviewer(model),
    )
    (sent,) = model.sent
    assert "second site" not in json.dumps(sent.messages)
    assert "Peatland plan" in env.outcome.statement

    marked = COMPLETE.model_copy(update={"documentation_is_plan": True})
    model = review_of(*every_requirement())
    asked = DmpReviewRequest(project_documents=[marked], project_plan_approved=written)
    run(runs_dir, asked, reviewer(model))
    (sent,) = model.sent
    assert "second site" in json.dumps(sent.messages)


def test_no_plan_attached_abstains(runs_dir: Path) -> None:
    env = run(runs_dir, DmpReviewRequest())
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


def test_without_a_model_there_is_no_review(runs_dir: Path) -> None:
    env = run(runs_dir, DmpReviewRequest(project_documents=[COMPLETE]))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.CAPABILITY_NOT_IMPLEMENTED
    assert "DD_DMP_MATCHER=template" in env.outcome.statement


@pytest.mark.parametrize(
    "reading",
    [
        (STORAGE.id, "partly", "words that the plan never says", "Not there."),
        (STORAGE.id, "fully", None, "Said to answer it, with no quote."),
        ("no-such-requirement", "not", None, "Made up."),
        (STORAGE.id, "not", None, "  "),
    ],
)
def test_a_reading_that_fails_its_checks_is_dropped_and_said(
    runs_dir: Path, reading: tuple[str, str, str | None, str]
) -> None:
    others = [i for i in every_requirement() if i[0] != STORAGE.id]
    model = review_of(reading, *others)
    env = run(runs_dir, DmpReviewRequest(project_documents=[COMPLETE]), reviewer(model))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    assert STORAGE.heading not in by_section(env)
    assert any(d.startswith(STORAGE.id) for d in env.payload_as(DmpDiscrepancies).dropped)


def test_a_requirement_read_twice_keeps_the_first_reading(runs_dir: Path) -> None:
    model = review_of(
        (STORAGE.id, "partly", BACKUP, "Only backup."),
        (STORAGE.id, "not", None, "Nothing."),
        *[i for i in every_requirement() if i[0] != STORAGE.id],
    )
    env = run(runs_dir, DmpReviewRequest(project_documents=[COMPLETE]), reviewer(model))
    assert by_section(env)[STORAGE.heading].finding == "vague"
    assert any("read twice" in d for d in env.payload_as(DmpDiscrepancies).dropped)


def test_an_unusable_reply_abstains_and_says_why(runs_dir: Path) -> None:
    model = FakeModel("not json")
    env = run(runs_dir, DmpReviewRequest(project_documents=[COMPLETE]), reviewer(model))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.CAPABILITY_NOT_IMPLEMENTED
    assert "schema" in env.outcome.statement


def test_a_reply_with_no_usable_reading_abstains(runs_dir: Path) -> None:
    model = review_of(("no-such-requirement", "not", None, "Made up."))
    env = run(runs_dir, DmpReviewRequest(project_documents=[COMPLETE]), reviewer(model))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert "none of its readings" in env.outcome.statement

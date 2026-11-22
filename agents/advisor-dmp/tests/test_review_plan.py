"""advisor.dmp reviews the plan a researcher attached (`setup.dmp-review`): by rule, against the
core requirements and the decisions made in the project, with a model's reading that may only
raise a finding (docs/specs/agents.md, Model-backed personas)."""

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
from dd_sdk.contract.facts import FactKind, ProjectDocument, ProjectFact, SensitivityDecision
from dd_sdk.contract.models import Derivation, Envelope, GroundingMode, OutcomeStatus, ReasonCode
from dd_sdk.model import declared
from dd_sdk.testing import FakeModel

PLANS = Path(__file__).parents[1] / "src" / "dd_agent_advisor_dmp" / "evals" / "data"
STORAGE = SECTIONS[2]
LEGAL = SECTIONS[3]
COLLECTION = SECTIONS[0]


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
    conductor = make_conductor(runs_dir, agent or DmpChecker())
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


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_a_plan_is_reviewed_by_rule_against_every_requirement(runs_dir: Path) -> None:
    env = run(runs_dir, DmpReviewRequest(project_documents=[attached("complete.md")]))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    found = by_section(env)
    assert list(found) == [s.heading for s in SECTIONS]
    assert found[STORAGE.heading].finding == "covered"
    quote = found[STORAGE.heading].quote
    assert quote is not None
    assert quote in " ".join(attached("complete.md").documentation_text.split())
    assert found[LEGAL.heading].finding == "missing"
    assert all(f.finding_derivation == Derivation.LEXICAL for f in found.values())
    payload = env.payload_as(DmpDiscrepancies)
    assert payload.limitations and not payload.discrepancies


def test_a_partial_plan_is_missing_what_it_has_no_heading_for(runs_dir: Path) -> None:
    found = by_section(run(runs_dir, DmpReviewRequest(project_documents=[attached("partial.md")])))
    assert found[LEGAL.heading].finding == "covered"
    assert found[STORAGE.heading].finding == "missing"


def test_a_decision_the_plan_does_not_name_is_a_conflict(runs_dir: Path) -> None:
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
    asked = DmpReviewRequest(
        project_documents=[attached("complete.md")], project_decisions=decisions
    )
    conflicts = run(runs_dir, asked).payload_as(DmpDiscrepancies).decision_conflicts
    kinds = {c.fact_kind for c in conflicts}
    # The plan names NERC (its data centre) but not the licence, and has no legal section.
    assert kinds == {FactKind.LICENCE, FactKind.SENSITIVITY}
    assert all(c.message for c in conflicts)


def test_no_plan_attached_abstains(runs_dir: Path) -> None:
    env = run(runs_dir, DmpReviewRequest())
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_a_model_may_raise_a_covered_finding_to_vague_with_a_quote_from_the_plan(
    runs_dir: Path,
) -> None:
    quote = "backed up nightly to a second site"
    model = FakeModel(readings((STORAGE.id, "partly", quote, "It says nothing of security.")))
    env = run(
        runs_dir, DmpReviewRequest(project_documents=[attached("complete.md")]), reviewer(model)
    )
    raised = by_section(env)[STORAGE.heading]
    assert raised.finding == "vague"
    assert raised.finding_derivation == Derivation.MODEL
    assert raised.reason and raised.quote == quote
    (sent,) = model.sent
    assert sent.system == REVIEW_PROMPT


def test_a_model_never_lowers_a_rules_finding(runs_dir: Path) -> None:
    model = FakeModel(
        readings(
            (LEGAL.id, "fully", "take soil cores at twelve plots", "The fieldwork is described."),
            (STORAGE.id, "fully", None, "Storage and backup are covered."),
        )
    )
    env = run(
        runs_dir, DmpReviewRequest(project_documents=[attached("complete.md")]), reviewer(model)
    )
    found = by_section(env)
    # Pointed to, but still missing, for a person to judge.
    assert found[LEGAL.heading].finding == "missing"
    assert found[LEGAL.heading].reason
    assert found[STORAGE.heading].finding == "covered"
    assert found[STORAGE.heading].finding_derivation == Derivation.LEXICAL


@pytest.mark.parametrize(
    "reading",
    [
        (STORAGE.id, "not", "words that the plan never says", "Not there."),
        ("no-such-requirement", "not", None, "Made up."),
        (STORAGE.id, "not", None, "  "),
    ],
)
def test_a_reading_that_fails_its_checks_is_dropped_and_said(
    runs_dir: Path, reading: tuple[str, str, str | None, str]
) -> None:
    model = FakeModel(readings(reading))
    env = run(
        runs_dir, DmpReviewRequest(project_documents=[attached("complete.md")]), reviewer(model)
    )
    payload = env.payload_as(DmpDiscrepancies)
    assert payload.dropped
    assert by_section(env)[STORAGE.heading].finding == "covered"


def test_an_unusable_reply_leaves_the_rules_review(runs_dir: Path) -> None:
    model = FakeModel("not json")
    env = run(runs_dir, DmpReviewRequest(project_documents=[attached("vague.md")]), reviewer(model))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    assert all(f.finding_derivation == Derivation.LEXICAL for f in by_section(env).values())
    assert COLLECTION.heading in by_section(env)

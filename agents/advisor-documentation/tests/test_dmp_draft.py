"""advisor.documentation drafts a Data Management Plan (`setup.dmp-create`, docs/specs/drafting.md):
to the template's core requirements, from what people in the project decided and the researcher's
answers, with no inventory needed, asking first, and with a model's suggestions offered beside the
questions and never written into the plan."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_documentation.plan import TITLE
from dd_agent_advisor_documentation.prose import ModelWriter
from dd_agent_advisor_documentation.suggestions import SUGGEST_DMP_PROMPT
from dd_agent_advisor_documentation.testing import suggestion_reply
from dd_dmp_template import SECTIONS
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.facts import FactKind, ProjectFact, SensitivityDecision
from dd_sdk.contract.models import (
    CurrentVersion,
    Derivation,
    Document,
    DocumentKind,
    DocumentVersionRef,
    DraftAnswer,
    DraftRequest,
    Envelope,
    GroundingMode,
    OutcomeStatus,
    ProjectDocument,
    VersionState,
    new_invocation_id,
)
from dd_sdk.testing import FakeModel

DECISIONS = [
    ProjectFact(fact_kind=FactKind.FUNDER, fact_subject="funder", fact_funder_name="NERC"),
    ProjectFact(fact_kind=FactKind.LICENCE, fact_subject="licence", licence_id="CC-BY-4.0"),
    ProjectFact(
        fact_kind=FactKind.REQUIRED_REPOSITORY,
        fact_subject="repository",
        fact_repository_name="NERC EDS Environmental Information Data Centre",
        fact_required_by=["NERC"],
    ),
    ProjectFact(
        fact_kind=FactKind.SENSITIVITY,
        fact_subject="nest sites",
        sensitive_subject="Locations of nest sites",
        sensitivity_decision=SensitivityDecision.GENERALISE,
    ),
]
PROPOSAL = "We will deposit the flux data in the EIDC within a year of the last field season."


def asked(**update: object) -> DraftRequest:
    """A plan's first request: no inventory, no answers, the decisions people made."""
    base = DraftRequest(document_kind=DocumentKind.DMP, project_decisions=DECISIONS)
    return base.model_copy(update=update)


def redrafted(given: DraftRequest, *answers: tuple[str, str]) -> DraftRequest:
    """`given` as a later run makes it: after the note, with the answers recorded."""
    note = CurrentVersion(
        version_ref=DocumentVersionRef(document_id=new_invocation_id(), version=1),
        document_title=TITLE,
        media_type="text/markdown",
        document_text="# Data Management Plan\n\n_This is not the plan yet._\n",
        version_state=VersionState.PROPOSED,
    )
    return given.model_copy(
        update={
            "current_version": note,
            "draft_answers": [DraftAnswer(answered_question=q, answer_text=a) for q, a in answers],
        }
    )


def proposal() -> ProjectDocument:
    return ProjectDocument(
        documentation_name="case-for-support.md",
        documentation_digest="b" * 64,
        documentation_media_type="text/markdown",
        documentation_size=len(PROPOSAL.encode()),
        documentation_added_at=datetime(2026, 11, 1, tzinfo=UTC),
        documentation_text=PROPOSAL,
    )


def draft(
    runs_dir: Path, given: DraftRequest, editor: DocumentationEditor | None = None
) -> tuple[Envelope, Document]:
    conductor = make_conductor(runs_dir, editor or DocumentationEditor())
    env = conductor.invoke(request("advisor.documentation", given), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.INPUT_ONLY
    assert conductor.grounding_reports[env.invocation_id].passed
    return env, env.payload_as(Document)


def headings(text: str) -> list[str]:
    return [line[3:] for line in text.splitlines() if line.startswith("## ")]


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_a_first_plan_asks_first_and_needs_no_inventory(runs_dir: Path) -> None:
    _, note = draft(runs_dir, asked())
    assert note.document_kind == DocumentKind.DMP
    assert note.document_stage == "questions"
    assert note.document_questions
    assert not headings(note.document_text)
    asked_about = {q.gap_section for q in note.document_questions}
    assert {s.heading for s in SECTIONS} <= asked_about


def test_the_plan_follows_the_template_and_places_decisions_and_answers_as_given(
    runs_dir: Path,
) -> None:
    _, note = draft(runs_dir, asked())
    storage = next(q for q in note.document_questions if q.gap_section == SECTIONS[2].heading)
    answer = "Data are kept on the university's research storage, backed up nightly."
    _, plan = draft(runs_dir, redrafted(asked(), (storage.question_id, answer)))

    assert plan.document_stage == "draft"
    assert plan.document_derivation == Derivation.TEMPLATE
    assert plan.media_type == "text/markdown"
    assert headings(plan.document_text) == [
        "Project details",
        *(s.heading for s in SECTIONS),
    ]
    text = plan.document_text
    assert answer in text
    for decided in ("NERC", "`CC-BY-4.0`", "Environmental Information Data Centre"):
        assert decided in text
    assert "Locations of nest sites: generalised" in text
    # The answered section is asked no more; every other gap is marked and asked.
    assert storage.question_id not in {q.question_id for q in plan.document_questions}
    for q in plan.document_questions:
        assert f"<!-- dd:gap {q.question_id} -->" in text


def test_a_decided_licence_is_offered_beside_the_sharing_question(runs_dir: Path) -> None:
    _, plan = draft(runs_dir, redrafted(asked()))
    sharing = next(q for q in plan.document_questions if q.gap_section == SECTIONS[4].heading)
    assert sharing.suggested_answer is not None and "CC-BY-4.0" in sharing.suggested_answer


def test_a_model_suggests_from_attached_documents_and_never_writes_the_plan(
    runs_dir: Path,
) -> None:
    given = redrafted(asked(project_documents=[proposal()]))
    _, template = draft(runs_dir, given)
    collection = next(
        q for q in template.document_questions if q.gap_section == SECTIONS[0].heading
    )
    model = FakeModel(suggestion_reply({collection.question_id: PROPOSAL}))
    editor = DocumentationEditor(writer=ModelWriter(model))
    _, plan = draft(runs_dir, given, editor)

    assert plan.document_text == template.document_text
    offered = {q.question_id: q for q in plan.document_questions if q.suggested_answer}
    assert offered[collection.question_id].suggestion_derivation == Derivation.MODEL
    assert PROPOSAL not in plan.document_text
    (sent,) = model.sent
    assert sent.system == SUGGEST_DMP_PROMPT
    assert "case-for-support.md" in str(sent.messages[0])


def test_without_attached_documents_no_model_is_asked(runs_dir: Path) -> None:
    model = FakeModel(suggestion_reply({}))
    _, plan = draft(runs_dir, redrafted(asked()), DocumentationEditor(writer=ModelWriter(model)))
    assert plan.document_stage == "draft"
    assert model.sent == []

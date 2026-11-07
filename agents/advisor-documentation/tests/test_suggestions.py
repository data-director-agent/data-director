"""advisor.documentation suggests a data dictionary's definitions and units as questions, never as
cell values (docs/specs/drafting.md, invariants 3 and 7): a model's suggestion is offered beside
its question, and becomes `supplied` only when a person records it as their answer."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest
from test_prose import MODEL, StubClient, draft, sample, template_draft

from dd_agent_advisor_documentation.agent import DocumentationEditor, Source
from dd_agent_advisor_documentation.prose import (
    MAX_SUGGESTION,
    SUGGEST_PROMPT,
    SUGGESTED_COLUMNS,
    AnthropicWriter,
    Ask,
    check_suggestions,
)
from dd_harness.conductor import Conductor
from dd_harness.projects import ProjectStore
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import (
    Derivation,
    Document,
    DocumentKind,
    DocumentQuestion,
    DraftAnswer,
    DraftRequest,
    OutcomeStatus,
)

DICTIONARY = "soil-survey.data-dictionary.draft.json"


def suggestible(document: Document) -> list[DocumentQuestion]:
    return [q for q in document.document_questions if q.gap_column in SUGGESTED_COLUMNS]


def suggestion_for(q: DocumentQuestion) -> str:
    return f"Suggested {q.gap_column} of {q.gap_field}"


def every_suggestion(document: Document) -> dict[str, str]:
    """A reply suggesting an answer to every question the template draft asks, of any column."""
    return {q.question_id: suggestion_for(q) for q in document.document_questions}


@pytest.mark.requirement("R5", "DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_a_suggestion_is_offered_with_its_question_and_never_written_into_a_cell(
    runs_dir: Path,
) -> None:
    asked = sample(DICTIONARY)
    template = template_draft(runs_dir, asked)
    env, grounded = draft(runs_dir, StubClient(every_suggestion(template)), asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED and grounded
    document = env.payload_as(Document)

    # The dictionary is the template's, to the byte: no suggestion reached a cell.
    assert document.document_text == template.document_text
    assert document.document_derivation == Derivation.TEMPLATE
    for q in document.document_questions:
        assert suggestion_for(q) not in document.document_text
    # The same questions are asked; each definition and unit carries the model's suggestion.
    ids = [q.question_id for q in document.document_questions]
    assert ids == [q.question_id for q in template.document_questions]
    for q in document.document_questions:
        if q.gap_column in SUGGESTED_COLUMNS:
            assert q.suggested_answer == suggestion_for(q)
            assert q.suggestion_derivation == Derivation.MODEL
        else:
            # A type, format or missing-value code is never suggested, whatever the model says.
            assert q.suggested_answer is None and q.suggestion_derivation is None
    assert suggestible(document)


@pytest.mark.requirement("R5")
def test_a_confirmed_suggestion_comes_back_supplied(runs_dir: Path) -> None:
    asked = sample(DICTIONARY)
    template = template_draft(runs_dir, asked)
    env, _ = draft(runs_dir, StubClient(every_suggestion(template)), asked)
    offered = suggestible(env.payload_as(Document))[0]
    assert offered.suggested_answer is not None

    confirmed = DraftAnswer(
        answered_question=offered.question_id, answer_text=offered.suggested_answer
    )
    again, _ = draft(
        runs_dir,
        StubClient(every_suggestion(template)),
        asked.model_copy(update={"draft_answers": [confirmed]}),
    )
    document = again.payload_as(Document)
    row = next(
        r
        for r in csv.DictReader(io.StringIO(document.document_text))
        if (r["file"], r["field"]) == (offered.gap_file, offered.gap_field)
    )
    column = offered.gap_column or ""
    assert (row[column], row[f"{column}_source"]) == (offered.suggested_answer, Source.SUPPLIED)
    assert offered.question_id not in {q.question_id for q in document.document_questions}


@pytest.mark.parametrize(
    ("suggestion", "why"),
    [
        ("x" * (MAX_SUGGESTION + 1), "too long"),
        ("See https://example.org/units", "names"),
        ("- metres", "not plain text"),
        ("metres<br>per second", "not plain text"),
        ("metres\nper second", "not plain text"),
        (42, "not text"),
    ],
)
def test_a_suggestion_that_is_not_one_plain_line_is_not_offered(
    suggestion: object, why: str
) -> None:
    ask = Ask("q-" + "0" * 16, "data/readings.csv", "depth_cm", "unit")
    got = check_suggestions(json.dumps({ask.question_id: suggestion}), {}, [ask])
    assert got.answers == {}
    assert len(got.dropped) == 1 and why in got.dropped[0]


def test_only_a_definition_or_unit_that_was_asked_is_offered() -> None:
    asks = [
        Ask("q-" + "0" * 16, "a.csv", "age_yrs", "description"),
        Ask("q-" + "1" * 16, "a.csv", "age_yrs", "missing_values"),
    ]
    reply = {
        asks[0].question_id: "The participant's age in years",
        asks[1].question_id: "-99",
        "q-" + "2" * 16: "years",
    }
    got = check_suggestions(json.dumps(reply), {}, asks)
    assert got.answers == {asks[0].question_id: "The participant's age in years"}
    assert len(got.dropped) == 2


@pytest.mark.parametrize(
    ("reply", "stop_reason"), [("not json", "end_turn"), ("[]", "end_turn"), ("{}", "refusal")]
)
def test_an_unusable_reply_suggests_nothing_and_changes_no_cell(
    runs_dir: Path, reply: str, stop_reason: str
) -> None:
    asked = sample(DICTIONARY)
    template = template_draft(runs_dir, asked)
    env, _ = draft(runs_dir, StubClient(reply, stop_reason), asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    document = env.payload_as(Document)
    assert document.document_text == template.document_text
    assert document.document_questions == template.document_questions


def test_the_model_is_given_the_facts_and_never_the_answers_or_descriptions(
    runs_dir: Path,
) -> None:
    asked = sample(DICTIONARY)
    template = template_draft(runs_dir, asked)
    secret = "Answered by the researcher in confidence"
    answered = suggestible(template)[0]
    asked = asked.model_copy(
        update={
            "draft_answers": [
                DraftAnswer(answered_question=answered.question_id, answer_text=secret)
            ]
        }
    )
    client = StubClient({})
    env, _ = draft(runs_dir, client, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    (sent,) = client.sent
    assert sent["system"] == SUGGEST_PROMPT
    content = sent["messages"][0]["content"]
    assert secret not in content
    # Asked only about the unanswered definitions and units.
    questions = json.loads(
        content.split("Questions you may suggest an answer to:\n", 1)[1].split("\n\nFacts:", 1)[0]
    )
    assert answered.question_id not in {q["question_id"] for q in questions}
    assert {q["column"] for q in questions} <= SUGGESTED_COLUMNS and questions
    descriptions = [
        c.field_description
        for f in (asked.inventory.inventory_files if asked.inventory else [])
        for c in f.file_fields
        if c.field_description
    ]
    for description in descriptions:
        assert description not in content
    # The call is recorded with the run.
    assert len(env.telemetry.model_calls) == 1 and env.telemetry.model_calls[0].model_id == MODEL


def test_the_template_path_suggests_nothing(runs_dir: Path) -> None:
    document = template_draft(runs_dir, sample(DICTIONARY))
    assert all(q.suggested_answer is None for q in document.document_questions)


@pytest.mark.requirement("R5")
def test_in_a_project_a_suggestion_counts_only_once_a_person_records_it(
    runs_dir: Path, tmp_path: Path
) -> None:
    """The issue's "done when" (#574): suggestions are kept with the version's questions, the
    dictionary holds none of them, and confirming one in the project fills its cell as supplied."""
    projects = ProjectStore(tmp_path / "projects")
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    given = sample(DICTIONARY).inventory
    assert given is not None
    inventory = given.model_dump(mode="json", exclude_none=True)
    projects.add_inventory(project, inventory, acted_for=TEST_PRINCIPAL, caused_by="test")
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")

    def conductor_with(reply: dict[str, str]) -> Conductor:
        editor = DocumentationEditor(
            writer=AnthropicWriter(client=StubClient(reply), model_id=MODEL)  # type: ignore[arg-type]
        )
        conductor = make_conductor(runs_dir, editor)
        conductor.projects = projects
        return conductor

    def draft_in(conductor: Conductor) -> Document:
        asked = request(
            "advisor.documentation", DraftRequest(document_kind=DocumentKind.DATA_DICTIONARY)
        ).model_copy(update={"conversation_id": conversation})
        env = conductor.invoke(asked, acting_for=TEST_PRINCIPAL)
        assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
        return env.payload_as(Document)

    plain = draft_in(make_conductor_template(runs_dir, projects))
    reply = every_suggestion(plain)
    first = draft_in(conductor_with(reply))
    assert first.document_text == plain.document_text
    offered = suggestible(first)
    assert offered and all(q.suggested_answer for q in offered)

    # The project keeps each suggestion with the question it was offered for.
    document = projects.documents(project)[-1]
    latest = document["versions"][-1]
    kept = {q["question_id"]: q.get("suggested_answer") for q in latest["questions"]}
    assert all(kept[q.question_id] == q.suggested_answer for q in offered)

    # The researcher confirms one suggestion and corrects another.
    confirm, correct = offered[0], offered[1]
    answers = [
        DraftAnswer(
            answered_question=confirm.question_id, answer_text=confirm.suggested_answer or ""
        ),
        DraftAnswer(
            answered_question=correct.question_id, answer_text="Corrected by the researcher"
        ),
    ]
    projects.answer(
        project,
        document["document_id"],
        latest["version"],
        answers,
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    again = draft_in(conductor_with(reply))
    rows = {(r["file"], r["field"]): r for r in csv.DictReader(io.StringIO(again.document_text))}
    for q, text in ((confirm, confirm.suggested_answer), (correct, "Corrected by the researcher")):
        column = q.gap_column or ""
        row = rows[(q.gap_file or "", q.gap_field or "")]
        assert (row[column], row[f"{column}_source"]) == (text, Source.SUPPLIED)
    # Every other suggestion is still only offered: no cell holds it.
    for q in suggestible(again):
        column = q.gap_column or ""
        row = rows[(q.gap_file or "", q.gap_field or "")]
        assert (row[column], row[f"{column}_source"]) == ("", Source.UNKNOWN)


def make_conductor_template(runs_dir: Path, projects: ProjectStore) -> Conductor:
    conductor = make_conductor(runs_dir, DocumentationEditor())
    conductor.projects = projects
    return conductor

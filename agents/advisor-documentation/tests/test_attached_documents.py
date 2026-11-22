"""advisor.documentation gives its model the documents a researcher attached, for suggestions only
(docs/specs/drafting.md, invariant 7): what field notes say may be offered beside a question, and
is never written into a draft or into its prose."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from test_prose import StubClient, draft, sample, template_draft

from dd_agent_advisor_documentation.prose import SYSTEM_PROMPT
from dd_agent_advisor_documentation.suggestions import (
    DOCUMENTS,
    MAX_DOCUMENTS,
    SUGGEST_PROMPT,
    SUGGEST_README_PROMPT,
    Ask,
    SuggestionReply,
    check_suggestions,
    with_documents,
)
from dd_sdk.contract.models import (
    Derivation,
    Document,
    DraftAnswer,
    DraftRequest,
    OutcomeStatus,
    ProjectDocument,
)

DICTIONARY = "soil-survey.data-dictionary.draft.json"
README = "soil-survey.readme.draft.json"
NOTES = "Soil cores were taken at 10 cm depth. See https://example.org/protocol for the method."


def attached(name: str, text: str) -> ProjectDocument:
    return ProjectDocument(
        documentation_name=name,
        documentation_digest="a" * 64,
        documentation_media_type="text/markdown",
        documentation_size=len(text.encode()),
        documentation_added_at=datetime(2026, 11, 1, tzinfo=UTC),
        documentation_text=text,
    )


def with_notes(asked: DraftRequest, *documents: ProjectDocument) -> DraftRequest:
    return asked.model_copy(
        update={"project_documents": list(documents) or [attached("fieldnotes.md", NOTES)]}
    )


def facts_sent(content: str) -> dict[str, Any]:
    found: dict[str, Any] = json.loads(content.split("\n\nFacts:\n", 1)[1])
    return found


@pytest.mark.requirement("R5", "DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_a_suggestion_may_come_from_an_attached_document_and_is_never_written(
    runs_dir: Path,
) -> None:
    asked = with_notes(sample(DICTIONARY))
    template = template_draft(runs_dir, asked)
    unit = next(q for q in template.document_questions if q.gap_column == "unit")
    client = StubClient({unit.question_id: "centimetres, as the field notes say"})
    env, grounded = draft(runs_dir, client, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED and grounded
    document = env.payload_as(Document)

    (sent,) = client.sent
    assert sent["system"] == SUGGEST_PROMPT
    [given] = facts_sent(sent["messages"][0]["content"])[DOCUMENTS]
    assert given == {"name": "fieldnotes.md", "text": NOTES}
    # Offered beside its question, never placed in a cell.
    [offered] = [q for q in document.document_questions if q.suggested_answer]
    assert offered.question_id == unit.question_id
    assert offered.suggestion_derivation == Derivation.MODEL
    assert document.document_text == template.document_text
    assert document.document_derivation == Derivation.TEMPLATE


def test_the_readme_prose_is_given_attached_documents_only_with_an_answer(
    runs_dir: Path,
) -> None:
    """Attached documents may inform a section the researcher answered, never one no one has."""
    asked = with_notes(sample(README))
    client = StubClient({}, suggestions={})
    env, _ = draft(runs_dir, client, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    by_system = {s["system"]: s["messages"][0]["content"] for s in client.sent}
    assert NOTES not in by_system[SYSTEM_PROMPT]
    assert DOCUMENTS in facts_sent(by_system[SUGGEST_README_PROMPT])

    # Once the researcher answers Methods, the prose is given their documents to write it from.
    template = template_draft(runs_dir, asked)
    (methods,) = [q for q in template.document_questions if q.gap_section == "Methods"]
    answer = DraftAnswer(answered_question=methods.question_id, answer_text="As my notes say.")
    client = StubClient({}, suggestions={})
    draft(runs_dir, client, asked.model_copy(update={"draft_answers": [answer]}))
    by_system = {s["system"]: s["messages"][0]["content"] for s in client.sent}
    assert NOTES in by_system[SYSTEM_PROMPT]


def test_without_attached_documents_the_model_is_given_none(runs_dir: Path) -> None:
    client = StubClient({})
    env, _ = draft(runs_dir, client, sample(DICTIONARY))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    (sent,) = client.sent
    assert DOCUMENTS not in facts_sent(sent["messages"][0]["content"])


def test_documents_are_given_latest_first_and_cut_to_fit() -> None:
    older = attached("protocol.md", "p" * MAX_DOCUMENTS)
    newer = attached("fieldnotes.md", "f" * (MAX_DOCUMENTS // 2))
    given = with_documents({}, with_notes(sample(DICTIONARY), older, newer))[DOCUMENTS]

    assert [d["name"] for d in given] == ["fieldnotes.md", "protocol.md"]
    assert "cut" not in given[0] and given[1]["cut"]
    assert sum(len(d["text"]) for d in given) == MAX_DOCUMENTS


def test_a_link_only_an_attached_document_gives_may_be_named() -> None:
    ask = Ask("q-0000000000000001", "data/readings.csv", "depth", "description")
    reply = SuggestionReply.model_validate(
        {
            "suggestions": [
                {
                    "question_id": ask.question_id,
                    "answer": "Depth; see https://example.org/protocol",
                }
            ]
        }
    )
    facts = with_documents({}, with_notes(sample(DICTIONARY)))

    assert check_suggestions(reply, facts, [ask]).answers
    assert not check_suggestions(reply, {}, [ask]).answers


def test_the_run_says_which_documents_the_model_was_given(runs_dir: Path) -> None:
    long_notes = attached("fieldnotes.md", "n" * (MAX_DOCUMENTS + 1))
    client = StubClient({})
    env, _ = draft(runs_dir, client, with_notes(sample(DICTIONARY), long_notes))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    assert "fieldnotes.md" in (env.outcome.statement or "")


def asked_sections(client: StubClient) -> set[str]:
    """The README sections the suggestion call asked about."""
    (sent,) = [s for s in client.sent if s["system"] == SUGGEST_README_PROMPT]
    content = sent["messages"][0]["content"]
    questions = json.loads(
        content.split("Questions you may suggest an answer to:\n", 1)[1].split("\n\nFacts:", 1)[0]
    )
    return {q["section"] for q in questions}


@pytest.mark.requirement("R5", "DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_methods_is_suggested_from_attached_documents_and_never_written(runs_dir: Path) -> None:
    asked = with_notes(sample(README))
    template = template_draft(runs_dir, asked)
    methods = next(q for q in template.document_questions if q.gap_section == "Methods")
    suggestion = "Soil cores were taken at 10 cm depth."
    client = StubClient({}, suggestions={methods.question_id: suggestion})
    env, grounded = draft(runs_dir, client, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED and grounded
    document = env.payload_as(Document)

    assert "Methods" in asked_sections(client)
    [offered] = [q for q in document.document_questions if q.gap_section == "Methods"]
    assert offered.suggested_answer == suggestion
    assert offered.suggestion_derivation == Derivation.MODEL
    assert suggestion not in document.document_text


def test_without_attached_documents_methods_is_never_asked(runs_dir: Path) -> None:
    client = StubClient({}, suggestions={})
    env, _ = draft(runs_dir, client, sample(README))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    assert asked_sections(client) and "Methods" not in asked_sections(client)


def test_a_methods_suggestion_naming_what_no_document_gives_is_not_offered() -> None:
    ask = Ask("q-0000000000000002", section="Methods", asks="how the data were collected.")
    reply = SuggestionReply.model_validate(
        {"suggestions": [{"question_id": ask.question_id, "answer": "Cores were taken at 25 cm."}]}
    )
    facts = with_documents({}, with_notes(sample(README)))

    got = check_suggestions(reply, facts, [ask])
    assert not got.answers and got.dropped

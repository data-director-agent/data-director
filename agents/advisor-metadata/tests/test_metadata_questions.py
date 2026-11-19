"""advisor.metadata asks about every value it leaves null, and places the answers a person recorded
(docs/specs/drafting.md, invariants 5 and 6), on its template path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_metadata_agent import draft, sample

from dd_agent_advisor_metadata.agent import load_form
from dd_agent_advisor_metadata.questions import gaps, question_id
from dd_sdk.contract.models import Document, DraftAnswer, OutcomeStatus


def drafted(runs_dir: Path, answers: list[DraftAnswer] | None = None) -> Document:
    asked = sample().model_copy(update={"draft_answers": answers or []})
    env, grounded = draft(runs_dir, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert grounded
    return env.payload_as(Document)


def value_at(record: dict[str, Any], path: str) -> Any:
    node: Any = record
    for part in path.replace("]", "").replace("[", ".").split("."):
        node = node[int(part)] if part.isdigit() else node[part]
    return node


def test_every_null_value_has_exactly_one_question_naming_it(runs_dir: Path) -> None:
    document = drafted(runs_dir)
    record = json.loads(document.document_text)
    asked = {q.gap_property or "": q for q in document.document_questions}
    nulls = [g.path for g in gaps(record)]
    assert nulls and sorted(asked) == sorted(nulls)
    for path, question in asked.items():
        assert path and value_at(record, path) is None
        assert question.question_id == question_id(path)
        assert question.gap_section is None and question.gap_file is None
        assert question.suggested_answer is None  # the template suggests nothing


def test_question_ids_are_the_same_in_every_draft(runs_dir: Path) -> None:
    first = [q.question_id for q in drafted(runs_dir).document_questions]
    again = [q.question_id for q in drafted(runs_dir).document_questions]
    assert first == again and len(set(first)) == len(first)


def test_an_answer_is_placed_as_given_and_asked_no_more(runs_dir: Path) -> None:
    before = drafted(runs_dir)
    title = next(q for q in before.document_questions if q.gap_property == "titles[0].title")
    answer = DraftAnswer(answered_question=title.question_id, answer_text="Soil survey, 2026")
    after = drafted(runs_dir, [answer])

    record = json.loads(after.document_text)
    assert record["titles"] == [{"title": "Soil survey, 2026"}]
    asked = {q.question_id for q in after.document_questions}
    assert title.question_id not in asked
    assert asked == {q.question_id for q in before.document_questions} - {title.question_id}


def test_an_answer_to_a_question_not_asked_or_left_blank_is_not_placed(runs_dir: Path) -> None:
    before = drafted(runs_dir)
    blank = before.document_questions[0].question_id
    answers = [
        DraftAnswer(answered_question="q-" + "f" * 16, answer_text="Anything"),
        DraftAnswer(answered_question=blank, answer_text="  "),
    ]
    after = drafted(runs_dir, answers)
    assert after.document_text == before.document_text
    assert after.document_questions == before.document_questions


def test_the_rule_table_marks_only_what_a_model_may_suggest() -> None:
    form = load_form()
    suggestable = {prop for prop, entry in form.items() if entry.suggest}
    # Who made it, when, under what rights and with whose money only the researcher can say.
    for prop in ("creators", "contributors", "dates", "rightsList", "fundingReferences"):
        assert prop not in suggestable
    assert all(form[prop].ask for prop in suggestable)

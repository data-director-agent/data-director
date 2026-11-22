"""Answers the researcher gave for another document, and facts people decided, offered as
suggestions in the metadata record (#1284, docs/specs/drafting.md, invariant 7): each beside its
question, derived as `answer`, never placed in the record."""

from __future__ import annotations

import json
from pathlib import Path

from test_metadata_agent import draft, sample

from dd_sdk.contract.facts import FactKind, ProjectFact
from dd_sdk.contract.models import (
    Derivation,
    Document,
    DocumentKind,
    DocumentQuestion,
    OutcomeStatus,
)
from dd_sdk.contract.questions import SharedAnswer, SharedField

README_TITLE = "q-" + "1" * 16
README_CREATORS = "q-" + "2" * 16


def shared(field: SharedField, text: str, question: str) -> SharedAnswer:
    return SharedAnswer(
        shared_field=field,
        answer_text=text,
        answered_question=question,
        answered_in=DocumentKind.README,
    )


GIVEN = [
    shared(SharedField.TITLE, "Soil cores from Hallam Moor", README_TITLE),
    shared(SharedField.CREATORS, "Smith, Jo", README_CREATORS),
]
FUNDER = ProjectFact(
    fact_kind=FactKind.FUNDER,
    fact_subject="Natural Environment Research Council",
    fact_funder_name="Natural Environment Research Council",
)


def drafted(runs_dir: Path, **given: object) -> tuple[Document, str]:
    asked = sample().model_copy(update=given)
    env, grounded = draft(runs_dir, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert grounded
    return env.payload_as(Document), env.outcome.statement


def by_path(document: Document) -> dict[str, DocumentQuestion]:
    return {q.gap_property or "": q for q in document.document_questions}


def test_the_questions_on_shared_fields_say_so(runs_dir: Path) -> None:
    asked = by_path(drafted(runs_dir)[0])
    assert asked["titles[0].title"].shared_field == SharedField.TITLE
    assert asked["creators[0].name"].shared_field == SharedField.CREATORS
    assert asked["fundingReferences[0].funderName"].shared_field == SharedField.FUNDER
    assert asked["rightsList[0].rights"].shared_field == SharedField.LICENCE
    assert asked["descriptions[0].description"].shared_field == SharedField.DESCRIPTION
    # A date created is not when the data were collected, which is all the README asks.
    assert asked["dates[0].date"].shared_field is None


def test_an_answer_from_the_readme_is_offered_and_not_placed(runs_dir: Path) -> None:
    document, statement = drafted(runs_dir, shared_answers=GIVEN, project_decisions=[FUNDER])
    asked = by_path(document)
    for path, text in (
        ("titles[0].title", "Soil cores from Hallam Moor"),
        ("creators[0].name", "Smith, Jo"),
        ("fundingReferences[0].funderName", "Natural Environment Research Council"),
    ):
        question = asked[path]
        assert question.suggested_answer == text
        assert question.suggestion_derivation == Derivation.ANSWER
        assert question.suggested_from in {"readme", "decision"}
    assert asked["fundingReferences[0].funderName"].suggested_from == "decision"
    # The record keeps the gap: nothing is supplied until the researcher saves it here.
    record = json.loads(document.document_text)
    assert record["titles"] == [{"title": None}]
    assert record["creators"][0]["name"] is None
    assert "suggestion" in statement


def test_without_shared_answers_nothing_is_offered(runs_dir: Path) -> None:
    document, _ = drafted(runs_dir)
    assert all(q.suggestion_derivation != Derivation.ANSWER for q in document.document_questions)

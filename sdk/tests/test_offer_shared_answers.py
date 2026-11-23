"""`dd_sdk.shared_answers`: a person's own answer, or a decided fact, offered beside a question on a
shared field, and never over a suggestion already made (#1284)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dd_sdk.contract.facts import FactKind, ProjectFact
from dd_sdk.contract.models import (
    Derivation,
    DocumentKind,
    DocumentQuestion,
)
from dd_sdk.contract.questions import SharedAnswer, SharedField
from dd_sdk.shared_answers import offer, offered

FUNDING = DocumentQuestion(
    question_id="q-" + "a" * 16,
    question_prompt="Who funded it?",
    gap_property="fundingReferences[0].funderName",
    shared_field=SharedField.FUNDER,
)
METHODS = DocumentQuestion(
    question_id="q-" + "b" * 16, question_prompt="How?", gap_section="Methods"
)
FUNDER = ProjectFact(fact_kind=FactKind.FUNDER, fact_subject="UKRI", fact_funder_name="UKRI")


def answered(text: str) -> SharedAnswer:
    return SharedAnswer(
        shared_field=SharedField.FUNDER,
        answer_text=text,
        answered_question="q-" + "c" * 16,
        answered_in=DocumentKind.README,
    )


def test_a_persons_answer_comes_before_a_decided_fact() -> None:
    [funding, methods] = offer([FUNDING, METHODS], [answered("AHRC")], [FUNDER])
    assert (funding.suggested_answer, funding.suggested_from) == ("AHRC", "readme")
    assert funding.suggestion_derivation == Derivation.ANSWER
    assert methods == METHODS
    assert offered([funding, methods]) == 1


def test_a_decided_fact_is_offered_where_nobody_answered() -> None:
    [funding] = offer([FUNDING], [answered("  ")], [FUNDER])
    assert (funding.suggested_answer, funding.suggested_from) == ("UKRI", "decision")


def test_a_suggestion_already_made_is_kept() -> None:
    made = FUNDING.model_copy(
        update={"suggested_answer": "NERC", "suggestion_derivation": Derivation.MODEL}
    )
    assert offer([made], [answered("AHRC")]) == [made]


def test_a_copied_suggestion_says_where_it_came_from_and_only_then() -> None:
    with pytest.raises(ValidationError):
        DocumentQuestion.model_validate(
            {**FUNDING.model_dump(), "suggested_answer": "x", "suggestion_derivation": "answer"}
        )
    with pytest.raises(ValidationError):
        DocumentQuestion.model_validate(
            {
                **FUNDING.model_dump(),
                "suggested_answer": "x",
                "suggestion_derivation": "model",
                "suggested_from": "readme",
            }
        )


def test_a_suggestion_from_the_institutions_profile_is_a_template_and_says_so() -> None:
    offered = {**FUNDING.model_dump(), "suggested_answer": "x"}
    DocumentQuestion.model_validate(
        {**offered, "suggestion_derivation": "template", "suggested_from": "institution"}
    )
    for wrong in (
        {"suggestion_derivation": "template"},
        {"suggestion_derivation": "model", "suggested_from": "institution"},
        {"suggestion_derivation": "answer", "suggested_from": "institution"},
    ):
        with pytest.raises(ValidationError):
            DocumentQuestion.model_validate({**offered, **wrong})

"""The discipline question suggests fields of study from the classification the deployment's
profile names, and is always answered in the researcher's own words (#1406)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_orchestrator import ScriptedModel, asks, conductor

from dd_agent_orchestrator_model.agent import ModelOrchestrator
from dd_agent_orchestrator_model.asking import (
    DISCIPLINE_KEY,
    FIELDS_OF_STUDY,
    NONE,
    suggest_fields,
)
from dd_harness.testing import PERMISSIVE, TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import Message, OutcomeStatus, Question, QuestionKind, Reply
from dd_subjects import SCHEMES, suggestions

pytestmark = pytest.mark.requirement("DD-CONVERSATION")

ASKED = "To find repositories for your field, I need your discipline."


def discipline(**changes: Any) -> dict[str, Any]:
    return {
        "question_key": DISCIPLINE_KEY,
        "question_kind": "short_text",
        "question_prompt": "What is the discipline or field of study of your research?",
        **changes,
    }


def asked(env: Any) -> list[Question]:
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    return env.payload_as(Reply).reply_questions or []


def with_settings(tmp_path: Path, written: str) -> Path:
    path = tmp_path / "profile.yaml"
    path.write_text(
        PERMISSIVE.read_text(encoding="utf-8")
        + f"agent_settings:\n  orchestrator.model:\n    {FIELDS_OF_STUDY}: {written}\n",
        encoding="utf-8",
    )
    return path


def test_the_card_offers_every_scheme_and_none() -> None:
    offered = ModelOrchestrator.spec.settings[FIELDS_OF_STUDY]
    assert set(offered.choices) == {*SCHEMES, NONE}
    assert offered.default in SCHEMES


def test_by_default_the_discipline_question_suggests_the_default_scheme(runs_dir: Path) -> None:
    model = ScriptedModel([asks(ASKED, ("ask_questions", {"questions": [discipline()]}))])
    env = conductor(runs_dir, model).invoke(
        request("orchestrator.model", Message(message_text="Where should I deposit?")),
        acting_for=TEST_PRINCIPAL,
    )
    [question] = asked(env)
    default = ModelOrchestrator.spec.settings[FIELDS_OF_STUDY].default
    assert question.question_kind is QuestionKind.SHORT_TEXT
    assert question.question_suggestions == suggestions(default)


@pytest.mark.parametrize("written", [*SCHEMES, NONE])
def test_the_profile_chooses_the_scheme_or_none(
    runs_dir: Path, tmp_path: Path, written: str
) -> None:
    model = ScriptedModel([asks(ASKED, ("ask_questions", {"questions": [discipline()]}))])
    c = make_conductor(runs_dir, ModelOrchestrator(model), profile=with_settings(tmp_path, written))
    env = c.invoke(
        request("orchestrator.model", Message(message_text="Where should I deposit?")),
        acting_for=TEST_PRINCIPAL,
    )
    [question] = asked(env)
    expected = None if written == NONE else suggestions(written)
    assert question.question_suggestions == expected


def test_a_discipline_asked_as_a_choice_is_shown_as_a_line_of_their_own_words() -> None:
    choice = Question.model_validate(
        discipline(
            question_kind="choice",
            question_options=[
                {"option_value": "a", "option_label": "Ecology"},
                {"option_value": "b", "option_label": "Hydrology"},
            ],
            question_other=True,
        )
    )
    shown = suggest_fields(choice, SCHEMES[0])
    assert shown.question_kind is QuestionKind.SHORT_TEXT
    assert shown.question_options is None
    assert shown.question_prompt == choice.question_prompt
    assert shown.question_suggestions == suggestions(SCHEMES[0])


def test_any_other_question_is_shown_as_asked() -> None:
    title = Question(
        question_key="title", question_prompt="Title?", question_kind=QuestionKind.SHORT_TEXT
    )
    assert suggest_fields(title, SCHEMES[0]) == title

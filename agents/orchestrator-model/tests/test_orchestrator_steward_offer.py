"""The orchestrator offers a data steward with a fixed choice, and raises nothing itself: the app
opens an escalation only once the researcher confirms (docs/specs/stewardship.md, invariant 5;
#375)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from test_orchestrator import ScriptedModel, asks, conductor

from dd_agent_orchestrator_model.steward_offer import NOT_NOW, SEND, STEWARD_KEY, STEWARD_QUESTION
from dd_harness.testing import TEST_PRINCIPAL, request
from dd_sdk.contract.models import Message, OutcomeStatus, Reply

pytestmark = pytest.mark.requirement("DD-CONVERSATION")


# The shapes a model gives the offer: as the prompt asks, with no options of its own, since the
# harness supplies them; with options of its own; and as another kind of question.
AS_THE_MODEL_ASKS = {
    "no options": {"question_kind": "choice"},
    "its own options": {
        "question_kind": "choice",
        "question_options": [
            {"option_value": "yes", "option_label": "Yes"},
            {"option_value": "yes", "option_label": "Yes, please"},
        ],
    },
    "a text question": {"question_kind": "short_text"},
}


def offered(runs_dir: Path, *questions: Mapping[str, object]) -> Reply:
    model = ScriptedModel(
        [asks("The agent could not help.", ("ask_questions", {"questions": list(questions)}))]
    )
    env = conductor(runs_dir, model).invoke(
        request("orchestrator.model", Message(message_text="Can I talk to someone?")),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    reply: Reply = env.payload_as(Reply)
    return reply


@pytest.mark.parametrize("given", AS_THE_MODEL_ASKS.values(), ids=AS_THE_MODEL_ASKS.keys())
def test_the_steward_offer_is_shown_with_its_fixed_options(
    runs_dir: Path, given: dict[str, object]
) -> None:
    """Whatever the model writes, the researcher is offered the fixed choice as a form, so the
    app can recognise the offer by its key and its answer by value."""
    own = {"question_key": STEWARD_KEY, "question_prompt": "Shall I email the steward?", **given}

    [question] = offered(runs_dir, own).reply_questions or []

    assert question == STEWARD_QUESTION
    assert {o.option_value for o in question.question_options or []} == {SEND, NOT_NOW}
    assert not question.question_other


def test_the_steward_offer_is_shown_beside_another_question(runs_dir: Path) -> None:
    other = {"question_key": "journal", "question_kind": "short_text", "question_prompt": "Which?"}
    own = {"question_key": STEWARD_KEY, "question_kind": "choice", "question_prompt": "Ask?"}

    questions = offered(runs_dir, other, own).reply_questions or []

    assert [q.question_key for q in questions] == ["journal", STEWARD_KEY]
    assert questions[1] == STEWARD_QUESTION


def test_the_prompt_says_when_to_offer_a_steward() -> None:
    prompt = (
        Path(__file__).parents[1] / "src" / "dd_agent_orchestrator_model" / "system_prompt.md"
    ).read_text(encoding="utf-8")
    assert f"`{STEWARD_KEY}`" in prompt

"""The orchestrator offers a data steward with a fixed choice, and raises nothing itself: the app
opens an escalation only once the researcher confirms (docs/specs/stewardship.md, invariant 5;
#375)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_orchestrator import ScriptedModel, asks, conductor

from dd_agent_orchestrator_model.steward_offer import NOT_NOW, SEND, STEWARD_KEY, STEWARD_QUESTION
from dd_harness.testing import TEST_PRINCIPAL, request
from dd_sdk.contract.models import Message, OutcomeStatus, Reply

pytestmark = pytest.mark.requirement("DD-CONVERSATION")


def test_the_steward_offer_is_shown_with_its_fixed_options(runs_dir: Path) -> None:
    """Whatever the model writes, the researcher is offered the fixed choice, so the app can
    recognise the offer by its key and its answer by value."""
    own = {
        "question_key": STEWARD_KEY,
        "question_kind": "short_text",
        "question_prompt": "Shall I email the steward for you?",
    }
    model = ScriptedModel(
        [asks("The agent could not help.", ("ask_questions", {"questions": [own]}))]
    )
    env = conductor(runs_dir, model).invoke(
        request("orchestrator.model", Message(message_text="Can I talk to someone?")),
        acting_for=TEST_PRINCIPAL,
    )

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    reply = env.payload_as(Reply)
    [question] = reply.reply_questions or []
    assert question == STEWARD_QUESTION
    assert {o.option_value for o in question.question_options or []} == {SEND, NOT_NOW}
    assert not question.question_other


def test_the_prompt_says_when_to_offer_a_steward() -> None:
    prompt = (
        Path(__file__).parents[1] / "src" / "dd_agent_orchestrator_model" / "system_prompt.md"
    ).read_text(encoding="utf-8")
    assert f"`{STEWARD_KEY}`" in prompt

"""The orchestrator offers a data steward with a fixed choice, and raises nothing itself: the app
opens an escalation only once the researcher confirms (docs/specs/stewardship.md, invariant 5;
#375)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from test_orchestrator import ScriptedModel, asks, call, conductor

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


STEWARD = {"question_key": STEWARD_KEY, "question_kind": "choice", "question_prompt": "Ask?"}
GREET = ("example_hello", {"greeted_name": "Ada"})


def replied(runs_dir: Path, model: ScriptedModel, **kwargs: object) -> Reply:
    env = conductor(runs_dir, model, **kwargs).invoke(
        request("orchestrator.model", Message(message_text="How will my data get a DOI?")),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    reply: Reply = env.payload_as(Reply)
    return reply


def test_an_offer_without_a_reply_after_an_agent_answered_is_sent_back(runs_dir: Path) -> None:
    """A bare offer would hide what the agent found: the model is asked to write its reply first,
    and the offer is shown beside it."""
    model = ScriptedModel(
        [
            call(GREET),
            call(("ask_questions", {"questions": [STEWARD]})),
            asks("The agent found part of it.", ("ask_questions", {"questions": [STEWARD]})),
        ]
    )

    reply = replied(runs_dir, model)

    [refused] = model.sent[2]["messages"][-1]["results"]
    assert refused["is_error"] is True
    assert reply.reply_text == "The agent found part of it."
    assert reply.reply_questions == [STEWARD_QUESTION]


def test_an_offer_without_a_reply_is_sent_back_even_without_an_agent(runs_dir: Path) -> None:
    model = ScriptedModel(
        [
            call(("ask_questions", {"questions": [STEWARD]})),
            asks("No agent can help with this.", ("ask_questions", {"questions": [STEWARD]})),
        ]
    )

    reply = replied(runs_dir, model)

    assert len(model.sent) == 2
    assert reply.reply_text == "No agent can help with this."


def test_a_preamble_to_a_delegation_is_not_the_reply(runs_dir: Path) -> None:
    model = ScriptedModel(
        [
            asks("Let me ask an agent.", GREET),
            call(("ask_questions", {"questions": [STEWARD]})),
            asks("It could not help.", ("ask_questions", {"questions": [STEWARD]})),
        ]
    )

    assert replied(runs_dir, model).reply_text == "It could not help."


def test_text_beside_the_models_own_tool_is_kept_for_the_reply(runs_dir: Path) -> None:
    """Text written beside recording the entry point, before the questions, is the reply."""
    model = ScriptedModel(
        [
            asks("The agent found that figshare assigns DOIs.", ("set_entry_point", {"entry": 1})),
            call(("ask_questions", {"questions": [STEWARD]})),
        ]
    )
    project = Message(
        message_text="How will my data get a DOI?",
        project_title_by_researcher=True,
        project_entry_by_researcher=False,
    )
    env = conductor(runs_dir, model).invoke(
        request("orchestrator.model", project), acting_for=TEST_PRINCIPAL
    )

    reply = env.payload_as(Reply)
    assert len(model.sent) == 2
    assert reply.reply_text == "The agent found that figshare assigns DOIs."
    assert reply.reply_questions == [STEWARD_QUESTION]


def test_at_the_limit_a_bare_offer_is_shown_and_the_run_ends(runs_dir: Path) -> None:
    model = ScriptedModel([call(GREET), call(("ask_questions", {"questions": [STEWARD]}))])

    reply = replied(runs_dir, model, max_delegations=1)

    assert len(model.sent) == 2
    assert reply.reply_questions == [STEWARD_QUESTION]
    assert reply.reply_text == STEWARD_QUESTION.question_prompt

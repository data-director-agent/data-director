"""Unsettled consent leaves a way on: the orchestrator offers a fixed choice to continue
provisionally, and reads the choice from the structured answer, not the words of the message
(docs/specs/orchestration.md, invariant 23; #1327)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_orchestrator import ScriptedModel, asks, conductor, say

from dd_agent_orchestrator_model.notes import PROVISIONAL_NOTE
from dd_agent_orchestrator_model.provisional import (
    CONSENT_KEY,
    CONSENT_QUESTION,
    PROVISIONAL,
    WAIT,
    chose_provisional,
)
from dd_harness.testing import TEST_PRINCIPAL, request
from dd_sdk.contract.models import (
    ConversationTurn,
    Message,
    OutcomeStatus,
    QuestionAnswer,
    Reply,
    ReplyAnswers,
    TurnRole,
)

pytestmark = pytest.mark.requirement("DD-CONVERSATION")

PAUSED = "Consent must be settled before sharing; ask your ethics staff."


def answered(values: list[str], text: str) -> Message:
    return Message(
        message_text=text,
        history=[ConversationTurn(role=TurnRole.AGENT, turn_text=PAUSED)],
        reply_answers=ReplyAnswers(
            answer_to="01890000-0000-7000-8000-000000000000",
            given_answers=[QuestionAnswer(answered_key=CONSENT_KEY, answer_values=values)],
        ),
    )


def sent_text(model: ScriptedModel) -> str:
    return str(model.sent[-1]["messages"][-1]["content"])


OWN_OPTIONS = {
    "question_options": [
        {"option_value": "yes", "option_label": "Yes"},
        {"option_value": "no", "option_label": "No"},
    ],
    "question_other": True,
}


@pytest.mark.parametrize("given", [{}, OWN_OPTIONS], ids=["no options", "its own options"])
def test_the_consent_question_is_shown_with_its_fixed_options(
    runs_dir: Path, given: dict[str, object]
) -> None:
    """Whatever options the model writes, or none, since the harness supplies them, the
    researcher is offered the fixed ones, so the answer can be read by its value."""
    own: dict[str, object] = {
        "question_key": CONSENT_KEY,
        "question_kind": "choice",
        "question_prompt": "Go on?",
        **given,
    }
    model = ScriptedModel([asks(PAUSED, ("ask_questions", {"questions": [own]}))])
    message = Message(message_text="I don't know yet whether consent covers sharing")
    env = conductor(runs_dir, model).invoke(
        request("orchestrator.model", message), acting_for=TEST_PRINCIPAL
    )

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    [question] = env.payload_as(Reply).reply_questions or []
    assert question == CONSENT_QUESTION
    assert {o.option_value for o in question.question_options or []} == {PROVISIONAL, WAIT}


def test_choosing_to_continue_provisionally_is_read_from_the_answer_not_the_text(
    runs_dir: Path,
) -> None:
    model = ScriptedModel([say("Provisional shortlist: ...")])
    message = answered([PROVISIONAL], "ok")  # no phrase about planning in the words
    env = conductor(runs_dir, model).invoke(
        request("orchestrator.model", message), acting_for=TEST_PRINCIPAL
    )

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert PROVISIONAL_NOTE in sent_text(model)


@pytest.mark.parametrize("values", [[WAIT], []])
def test_waiting_or_not_choosing_sends_no_provisional_note(
    runs_dir: Path, values: list[str]
) -> None:
    model = ScriptedModel([say("We will wait.")])
    message = (
        answered(values, "Continue provisionally (planning only)")
        if values
        else Message(message_text="Continue provisionally please")
    )
    conductor(runs_dir, model).invoke(
        request("orchestrator.model", message), acting_for=TEST_PRINCIPAL
    )

    assert PROVISIONAL_NOTE not in sent_text(model)


def test_the_choice_holds_on_later_turns(runs_dir: Path) -> None:
    """The lone answer is written into the history as its option's label, so a later turn still
    knows that the researcher chose to continue provisionally."""
    label = next(
        o.option_label
        for o in CONSENT_QUESTION.question_options or []
        if o.option_value == PROVISIONAL
    )
    model = ScriptedModel([say("Here is a provisional README.")])
    message = Message(
        message_text="Draft the README",
        history=[
            ConversationTurn(role=TurnRole.AGENT, turn_text=PAUSED),
            ConversationTurn(role=TurnRole.USER, turn_text=label),
            ConversationTurn(role=TurnRole.AGENT, turn_text="Provisional shortlist: ..."),
        ],
    )
    conductor(runs_dir, model).invoke(
        request("orchestrator.model", message), acting_for=TEST_PRINCIPAL
    )

    assert PROVISIONAL_NOTE in sent_text(model)


@pytest.mark.parametrize("chosen_before", [False, True])
def test_answers_to_other_questions_neither_make_nor_hide_the_choice(chosen_before: bool) -> None:
    """An answer to another question is not the choice; nor does it hide one already made."""
    label = next(
        o.option_label
        for o in CONSENT_QUESTION.question_options or []
        if o.option_value == PROVISIONAL
    )
    history = [ConversationTurn(role=TurnRole.AGENT, turn_text=PAUSED)]
    if chosen_before:
        history.append(ConversationTurn(role=TurnRole.USER, turn_text=label))
    message = Message(
        message_text="2",
        history=history,
        reply_answers=ReplyAnswers(
            answer_to="01890000-0000-7000-8000-000000000000",
            given_answers=[QuestionAnswer(answered_key="entry", answer_values=["2"])],
        ),
    )

    assert chose_provisional(message) is chosen_before

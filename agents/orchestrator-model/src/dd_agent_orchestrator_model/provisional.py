"""The way on when consent is not settled (#1327): the orchestrator pauses the sharing steps, and
offers the researcher one fixed choice, to continue provisionally with planning-only advice or to
wait. The choice is read from the structured answer, never from the words of the message, so a
click is enough (docs/specs/orchestration.md, invariant 23).

Building and depositing the package stay blocked whatever is chosen: they wait for the
confirmation before packaging, which covers participants' consent
(`dd_harness.deposit_review.CONFIRMATIONS`).
"""

from __future__ import annotations

from typing import Final

from dd_agent_orchestrator_model.steward_offer import STEWARD_KEY, STEWARD_QUESTION
from dd_sdk.contract.models import ChoiceOption, Message, Question, QuestionKind, TurnRole

CONSENT_KEY: Final = "consent-provisional"
PROVISIONAL: Final = "provisional"
WAIT: Final = "wait"

CONSENT_QUESTION: Final = Question(
    question_key=CONSENT_KEY,
    question_prompt="Consent is not settled yet. How would you like to go on?",
    question_kind=QuestionKind.CHOICE,
    question_options=[
        ChoiceOption(
            option_value=PROVISIONAL,
            option_label="Continue provisionally (planning only)",
            option_help=(
                "Get a repository shortlist, README and metadata to plan with, each marked as "
                "provisional. Nothing is built or deposited until consent is settled."
            ),
        ),
        ChoiceOption(
            option_value=WAIT,
            option_label="Wait until consent is settled",
            option_help="Pause the sharing steps until you have checked consent.",
        ),
    ],
)

_LABEL: Final = next(
    o.option_label for o in CONSENT_QUESTION.question_options or [] if o.option_value == PROVISIONAL
)


def chose_provisional(message: Message) -> bool:
    """Whether the researcher chose to continue provisionally: in the answers this message
    carries, or as the lone answer of an earlier turn, whose words are the option's label."""
    given = message.reply_answers.given_answers if message.reply_answers else []
    for answer in given:
        if answer.answered_key == CONSENT_KEY:
            return PROVISIONAL in answer.answer_values
    return any(
        turn.role == TurnRole.USER and turn.turn_text.strip() == _LABEL for turn in message.history
    )


_FIXED: Final = {CONSENT_KEY: CONSENT_QUESTION, STEWARD_KEY: STEWARD_QUESTION}


def fixed(question: Question) -> Question:
    """The question as it is shown: a reserved question (the consent choice, the offer of a data
    steward) always in its own words and values, so that the answer can be read without reading
    the model's wording."""
    return _FIXED.get(question.question_key, question)

"""The orchestrator's offer of a data steward (#375): when it or an agent cannot help, it offers
the researcher one fixed choice, to ask a data steward or not now. The orchestrator raises
nothing: the app opens the escalation only once the researcher has seen what will be shared and
sent it (docs/specs/stewardship.md, invariant 5: the agent offers; a person confirms).
"""

from __future__ import annotations

from typing import Final

from dd_sdk.contract.models import ChoiceOption, Question, QuestionKind

STEWARD_KEY: Final = "ask-steward"
SEND: Final = "send"
NOT_NOW: Final = "not-now"

STEWARD_QUESTION: Final = Question(
    question_key=STEWARD_KEY,
    question_prompt="Would you like to ask a data steward?",
    question_kind=QuestionKind.CHOICE,
    question_options=[
        ChoiceOption(
            option_value=SEND,
            option_label="Ask a data steward",
            option_help=(
                "You will see what would be shared with your institution's data stewards, and "
                "can change your note before you send it."
            ),
        ),
        ChoiceOption(
            option_value=NOT_NOW,
            option_label="Not now",
            option_help="Nothing is sent. You can ask a data steward later from the project.",
        ),
    ],
)

"""What a conversational agent's reply asks the researcher: `Question`, its `ChoiceOption`s and
its `QuestionKind`, with the bounds on questions and answers (docs/specs/contract.md, rule 23).
Split from `models`, which re-exports every name here, to keep that module within its size limit.
Field names and enum values are the LinkML schema's.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from dd_sdk.contract.base import Frozen

# A choice question offers between 2 and 12 options (Question.question_options).
CHOICE_OPTIONS_MIN = 2
CHOICE_OPTIONS_MAX = 12
# An answer in the researcher's own words: one line for a short text question, several for a
# long one; a choice question's own-words answer is held to the short bound (QuestionAnswer).
SHORT_TEXT_MAX = 200
LONG_TEXT_MAX = 4000
# A short text question suggests at most this many answers (Question.question_suggestions): enough
# for a classification's top two levels, such as the ANZSRC Fields of Research.
QUESTION_SUGGESTIONS_MAX = 300
# A question's identifier within its reply (Question.question_key, QuestionAnswer.answered_key).
QUESTION_KEY_PATTERN = r"^[a-z][a-z0-9-]{0,39}$"


class QuestionKind(StrEnum):
    CHOICE = "choice"
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"


class ChoiceOption(Frozen):
    """One option of a choice question. The value is a string: a number would reach the agent as
    a floating-point value over A2A."""

    option_value: str
    option_label: str
    option_help: str | None = None


class Question(Frozen):
    """One question a reply asks, shown as a form field. A choice question has fixed options, of
    which one or several may be chosen, and may be answered in the researcher's own words where
    `question_other` is true; a short or long text question is answered in their own words and
    has no options. A short text question may suggest answers, of which the researcher may take
    one or write their own."""

    question_key: str = Field(pattern=QUESTION_KEY_PATTERN)
    question_prompt: str
    question_kind: QuestionKind
    question_help: str | None = None
    # The bounds are not in the schema (#333).
    question_options: list[ChoiceOption] | None = Field(
        default=None, min_length=CHOICE_OPTIONS_MIN, max_length=CHOICE_OPTIONS_MAX
    )
    question_multiple: bool = False
    question_other: bool = False
    question_suggestions: list[str] | None = Field(
        default=None, min_length=1, max_length=QUESTION_SUGGESTIONS_MAX
    )

    @model_validator(mode="after")
    def _options_fit_the_kind(self) -> Question:
        if self.question_kind is QuestionKind.CHOICE:
            if self.question_options is None:
                raise ValueError("a choice question has options")
            values = [o.option_value for o in self.question_options]
            if len(set(values)) != len(values):
                raise ValueError("each option of a choice question has a value of its own")
        elif self.question_options is not None or self.question_multiple or self.question_other:
            raise ValueError("only a choice question has options")
        if self.question_suggestions is not None:
            if self.question_kind is not QuestionKind.SHORT_TEXT:
                raise ValueError("only a short text question suggests answers")
            if any(not 0 < len(s.strip()) <= SHORT_TEXT_MAX for s in self.question_suggestions):
                raise ValueError("each suggested answer is a line a short text answer could be")
        return self

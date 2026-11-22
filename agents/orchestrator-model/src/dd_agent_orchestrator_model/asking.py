"""The questions a reply asks, as they are shown, and the reply's text when it only asks.

Suggested fields of study for the discipline question (#1406): when the orchestrator asks for
the researcher's discipline, it asks with the reserved question key `discipline`. The question is
shown as one line in the researcher's own words, with the fields of a published subject
classification as suggestions they may take or ignore: no list is required, because each
registry downstream uses its own. Which classification, if any, is the deployment's choice,
through this agent's `fields_of_study` setting (the profile's `agent_settings`,
docs/specs/policy-and-identity.md). The suggestions come from `dd_subjects`, never from the
model.
"""

from __future__ import annotations

from typing import Final

from dd_sdk.agent import AgentSpec, RunContext, Setting, setting
from dd_sdk.contract.models import Question, QuestionKind
from dd_subjects import SCHEMES, suggestions

DISCIPLINE_KEY: Final = "discipline"
FIELDS_OF_STUDY: Final = "fields_of_study"
NONE: Final = "none"

FIELDS_OF_STUDY_SETTING: Final = Setting(
    (*SCHEMES, NONE),
    "anzsrc-for",
    "The subject classification whose fields are suggested when the researcher is asked for "
    "their discipline: anzsrc-for (ANZSRC 2020 Fields of Research, divisions and groups) or "
    "oecd-fos (OECD Fields of R&D, Frascati Manual 2015). The researcher may always answer "
    "in their own words. None: no suggestions.",
)


def suggest_fields(question: Question, scheme_id: str) -> Question:
    """The question as it is shown: the discipline question as one line in the researcher's own
    words, with the fields of `scheme_id` suggested unless it is `none`; any other question as
    asked."""
    if question.question_key != DISCIPLINE_KEY:
        return question
    return Question(
        question_key=DISCIPLINE_KEY,
        question_prompt=question.question_prompt,
        question_kind=QuestionKind.SHORT_TEXT,
        question_help=question.question_help,
        question_suggestions=None if scheme_id == NONE else suggestions(scheme_id),
    )


def shown(asked: list[Question] | None, ctx: RunContext, spec: AgentSpec) -> list[Question] | None:
    """The questions the model asked, as the researcher is shown them: the discipline question
    with the fields of the scheme this invocation's settings name."""
    scheme_id = setting(ctx, spec, FIELDS_OF_STUDY)
    return [suggest_fields(q, scheme_id) for q in asked] if asked else None


def reply_text(text: str, questions: list[Question] | None) -> str:
    """The reply's text, or, when the model wrote none beside its questions, the lone question or
    how many there are."""
    if not questions or text:
        return text
    if len(questions) == 1:
        return questions[0].question_prompt
    return f"I have {len(questions)} questions for you."

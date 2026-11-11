"""Where a project's intake stands, derived from its log on every read and never stored
(docs/specs/projects.md, rule 20; docs/specs/orchestration.md, invariant 20).

The questions are Blueprint data in `dd_sdk.intake`. The answers are events of the project log,
written by `Projects.answer_intake` and `Projects.dismiss_intake`. An answer to the entry
question is an `entry_chosen`, the same as the phase tracker's, so any entry point recorded,
whether the researcher chose it or an orchestrator's model worked it out, answers that question.
Each other answer is an `intake_answered`, and the latest answer to a question counts.

The intake is pending while a question asked from the project's entry point is unanswered,
complete once none is, and dismissed from an `intake_dismissed` until an answer is recorded after
it. A turn sent while the intake is pending is not an answer and leaves it pending.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final, Literal

from dd_harness.answers import question_answer_problem
from dd_harness.progress import (
    ENTRY_CHOSEN,
    INTAKE_ANSWERED,
    INTAKE_DISMISSED,
    entry_chosen,
    intake_answers,
)
from dd_sdk.contract.models import QuestionAnswer
from dd_sdk.intake import ENTRY, INTAKE, IntakeQuestion, question

PENDING: Final = "pending"
COMPLETE: Final = "complete"
DISMISSED: Final = "dismissed"
type IntakeState = Literal["pending", "complete", "dismissed"]


def answered(events: Iterable[Mapping[str, Any]]) -> frozenset[str]:
    """The intake questions the log holds an answer to."""
    events = list(events)
    entry = {ENTRY} if entry_chosen(events) is not None else set()
    return frozenset(entry | intake_answers(events).keys())


def dismissed(events: Iterable[Mapping[str, Any]]) -> bool:
    """Whether the intake was dismissed and no answer has been recorded since."""
    for event in reversed(list(events)):
        if event["event"] == INTAKE_DISMISSED:
            return True
        if event["event"] in (ENTRY_CHOSEN, INTAKE_ANSWERED):
            return False
    return False


def next_question(events: Iterable[Mapping[str, Any]]) -> IntakeQuestion | None:
    """The first question asked from the project's entry point that has no answer, or None when
    the intake is complete or dismissed."""
    events = list(events)
    if dismissed(events):
        return None
    entry, done = entry_chosen(events), answered(events)
    return next((q for q in INTAKE if q.asked_at(entry) and q.id not in done), None)


def state(events: Iterable[Mapping[str, Any]]) -> IntakeState:
    """Whether the intake is pending, complete or dismissed."""
    events = list(events)
    if dismissed(events):
        return DISMISSED
    return PENDING if next_question(events) is not None else COMPLETE


def answer_problem(question_id: str, answer_values: Sequence[str], entry: int | None) -> str | None:
    """Why an answer choosing `answer_values` cannot be recorded for the question in a project at
    `entry`, or None if it can. The question must be one of the intake's, asked from `entry`, and
    the answer must fit it by the rules a turn's answer is checked by."""
    try:
        asked = question(question_id)
    except KeyError:
        return f"not a question of the intake: {question_id}"
    if not asked.asked_at(entry):
        return f"{question_id} is not asked from the project's entry point"
    as_question = asked.as_question()
    answer = QuestionAnswer(
        answered_key=as_question.question_key, answer_values=list(answer_values)
    )
    if problem := question_answer_problem(as_question, answer):
        return f"{question_id}: {problem}"
    return None

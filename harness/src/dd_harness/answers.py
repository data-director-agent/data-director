"""Whether one answer fits the question it answers (docs/specs/orchestration.md, invariant 16).

The same rules check a researcher's answer to a question a turn's `Reply` asked
(`dd_harness.conversations.answer_problem`) and their answer to a question of the project intake
(`dd_harness.intake`, docs/specs/projects.md, rule 20), where no turn is involved.
"""

from __future__ import annotations

from dd_sdk.contract.models import (
    LONG_TEXT_MAX,
    SHORT_TEXT_MAX,
    Question,
    QuestionAnswer,
    QuestionKind,
)


def question_answer_problem(question: Question, answer: QuestionAnswer) -> str | None:
    """Why `answer` does not fit `question`, or None if it does.

    A choice answer's values are options of its question, each chosen once and at most one
    unless several may be chosen, with words in place of an option only where the question
    allows it; a text answer is words alone, within its kind's length; and every answer chooses
    or says something."""
    words = (answer.answer_words or "").strip()
    if answer.answer_words is not None and not words:
        return "the answer in the researcher's own words is empty"
    if question.question_kind is not QuestionKind.CHOICE:
        limit = (
            SHORT_TEXT_MAX if question.question_kind is QuestionKind.SHORT_TEXT else LONG_TEXT_MAX
        )
        if answer.answer_values:
            return "the question takes words, not options"
        if not words:
            return "nothing is said"
        if len(words) > limit:
            return f"the answer is longer than {limit} characters"
        if question.question_kind is QuestionKind.SHORT_TEXT and "\n" in words:
            return "the answer is more than one line"
        return None
    offered = {o.option_value for o in question.question_options or []}
    unknown = [v for v in answer.answer_values if v not in offered]
    if unknown:
        return f"not an option of the question: {', '.join(unknown)}"
    if len(set(answer.answer_values)) != len(answer.answer_values):
        return "an option is chosen more than once"
    if words and not question.question_other:
        return "the question takes only its options"
    if len(words) > SHORT_TEXT_MAX:
        return f"the answer is longer than {SHORT_TEXT_MAX} characters"
    chosen = len(answer.answer_values) + (1 if words else 0)
    if chosen == 0:
        return "nothing is chosen"
    if chosen > 1 and not question.question_multiple:
        return "the question takes one answer"
    return None

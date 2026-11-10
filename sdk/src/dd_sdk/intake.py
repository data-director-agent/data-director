"""The project intake: the few questions that place a new project in the process flow (§8).

Before the first turn of a project with no entry point, Data Director asks first. The first
question is which entry point applies (§8.1); the rest are the §8 decision points that let a step
be skipped: whether there is a Data Management Plan, whether the data are sensitive, and whether a
repository is mandated. Each, apart from the first, is asked only from the entry points that reach
its step (docs/specs/orchestration.md, invariant 20).

This is Blueprint data, the same for every deployment, beside `dd_sdk.process_flow`. It names no
agent and runs no orchestrator. The harness records the answers in the project log and derives
step states from them (docs/specs/projects.md, rule 20), TODO(#667); the app shows the questions
one at a time, TODO(#668).

An answer of "No" marks the question's steps skipped. "Yes" and "Not sure" mark nothing: saying a
plan exists is not the check of a deposit against it, so the intake never shows a step as done.
Each question is a single choice with fixed options and no "Something else": an answer in the
researcher's own words is one no step state can follow, and the researcher may always type instead.

The wording, the entry points each question is asked from and the steps a "No" skips await a
Blueprint reading, TODO(#670).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from dd_sdk.contract.models import ChoiceOption, ChoiceQuestion
from dd_sdk.process_flow import ENTRIES

# The first question's id: its answer is the project's entry point (`entry_chosen`), not an
# `intake_answered` event (docs/specs/projects.md, rule 20).
ENTRY = "intake.entry"

# The option values of the yes-or-no questions.
YES = "yes"
NO = "no"
NOT_SURE = "not-sure"


@dataclass(frozen=True)
class IntakeOption:
    value: str
    label: str
    # The steps this answer marks skipped; empty for an answer that marks nothing.
    skips: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntakeQuestion:
    # A stable label, `intake.<name>`, that the project log records with the answer.
    id: str
    prompt: str
    options: tuple[IntakeOption, ...]
    # The entry points (their numbers) the question is asked from.
    asked_from: tuple[int, ...]

    def asked_at(self, entry: int | None) -> bool:
        """Whether the question is asked of a project at `entry`; the entry question always is."""
        return self.id == ENTRY or entry in self.asked_from

    def skips(self, values: Iterable[str]) -> frozenset[str]:
        """The steps an answer choosing `values` marks skipped."""
        chosen = set(values)
        return frozenset(s for o in self.options if o.value in chosen for s in o.skips)

    def choice_question(self) -> ChoiceQuestion:
        """The question as the core `ChoiceQuestion` the app draws (docs/specs/contract.md)."""
        return ChoiceQuestion(
            question_prompt=self.prompt,
            question_options=[
                ChoiceOption(option_value=o.value, option_label=o.label) for o in self.options
            ],
        )


def _yes_no(
    question_id: str, prompt: str, asked_from: tuple[int, ...], skips: tuple[str, ...]
) -> IntakeQuestion:
    return IntakeQuestion(
        question_id,
        prompt,
        (
            IntakeOption(YES, "Yes"),
            IntakeOption(NO, "No", skips),
            IntakeOption(NOT_SURE, "Not sure"),
        ),
        asked_from,
    )


# The intake's questions, in the order they are asked.
INTAKE: tuple[IntakeQuestion, ...] = (
    IntakeQuestion(
        ENTRY,
        "Where are you with your research data?",
        tuple(IntakeOption(str(e.number), f"{e.text[0].upper()}{e.text[1:]}") for e in ENTRIES),
        tuple(e.number for e in ENTRIES),
    ),
    _yes_no(
        "intake.dmp",
        "Do you have a Data Management Plan for this project?",
        (1, 2),
        ("governance.dmp",),
    ),
    _yes_no(
        "intake.sensitive",
        "Does the data include personal or otherwise sensitive information?",
        (1, 2),
        ("governance.sensitive-data-identify", "governance.sensitive-data-handle"),
    ),
    _yes_no(
        "intake.repository-mandated",
        "Has a funder, journal or institution said where the data must go?",
        (1, 2, 3),
        ("repository.mandated",),
    ),
)


def question(question_id: str) -> IntakeQuestion:
    for q in INTAKE:
        if q.id == question_id:
            return q
    raise KeyError(f"the intake has no question {question_id}")

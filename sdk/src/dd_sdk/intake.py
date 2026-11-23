"""The project intake: the few questions that place a new project in the process flow (§8).

Before the first turn of a project with no entry point, Data Director asks first. The first
question is which entry point applies (§8.1); the rest are the §8 decision points that let a step
be skipped: whether there is a Data Management Plan, whether the data are sensitive, and whether a
repository is mandated. Each, apart from the first, is asked only from the entry points that reach
its step (docs/specs/orchestration.md, invariant 20).

This is Blueprint data, the same for every deployment, beside `dd_sdk.process_flow`. It names no
agent and runs no orchestrator. The harness records the answers in the project log and derives
step states from them (docs/specs/projects.md, rule 20, `dd_harness.intake`); the app shows the
questions one at a time (docs/specs/app.md, rule 25).

Each answer may mark steps skipped, and none ever marks a step done: saying a plan exists is not
the check of a deposit against it, so the intake never shows a step as done. "Not sure" marks
nothing. The mandated-repository question follows §8's two branches (Figure 3): "No" marks the
check of whether a repository is mandated skipped, and "Yes" marks the recommendation of one
skipped, since the choice is made. The Data Management Plan question follows Figure 1's two
branches: "Yes" marks creating a plan skipped and "No" marks reviewing one skipped. The skip
records the branch not taken, not work, and once a plan written in the project after "No" is
approved, the harness lifts the review's skip (docs/specs/projects.md, rule 20). An
answer may also
carry a notice, which the app shows at once. "No" to a Data Management Plan says that writing one
is optional and still available, since an optional step is never suggested. "Yes" to sensitive
data says not to share the data itself with the agent, as §5.2 asks that sensitive data not reach
the model without institutional authorisation and Figure 2 asks that it be anonymised first in a
cloud deployment.

Each question is a single choice with fixed options and no "Something else": an answer in the
researcher's own words is one no step state can follow, and the researcher may always type instead.
The question set is the same for every deployment: a profile may not change or extend it.

The Blueprint reading that checked the wording, the entry points and the steps is
docs/specs/intake-reading.md.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from dd_sdk.contract.models import ChoiceOption, Question, QuestionKind
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
    # What the app says to the researcher at once on this answer; empty for none. It marks no step.
    notice: str = ""


@dataclass(frozen=True)
class IntakeQuestion:
    # A stable label, `intake.<name>`, that the project log records with the answer.
    id: str
    prompt: str
    options: tuple[IntakeOption, ...]
    # The entry points (their numbers) the question is asked from.
    asked_from: tuple[int, ...]
    # The step the question's decision sits before in §8's figures, where the journey map draws
    # it; empty for the entry question, which the map draws as the entry points themselves.
    before: str = ""

    def asked_at(self, entry: int | None) -> bool:
        """Whether the question is asked of a project at `entry`; the entry question always is."""
        return self.id == ENTRY or entry in self.asked_from

    def skips(self, values: Iterable[str]) -> frozenset[str]:
        """The steps an answer choosing `values` marks skipped."""
        chosen = set(values)
        return frozenset(s for o in self.options if o.value in chosen for s in o.skips)

    def as_question(self) -> Question:
        """The question as the core `Question` of kind choice the app draws
        (docs/specs/contract.md), keyed by its id without the `intake.` prefix."""
        return Question(
            question_key=self.id.removeprefix("intake."),
            question_prompt=self.prompt,
            question_kind=QuestionKind.CHOICE,
            question_options=[
                ChoiceOption(option_value=o.value, option_label=o.label) for o in self.options
            ],
        )


def _yes_no(
    question_id: str,
    prompt: str,
    asked_from: tuple[int, ...],
    *,
    yes: tuple[str, ...] = (),
    no: tuple[str, ...] = (),
    notices: Mapping[str, str] | None = None,
    before: str,
) -> IntakeQuestion:
    said = notices or {}
    return IntakeQuestion(
        question_id,
        prompt,
        (
            IntakeOption(YES, "Yes", yes, said.get(YES, "")),
            IntakeOption(NO, "No", no, said.get(NO, "")),
            IntakeOption(NOT_SURE, "Not sure"),
        ),
        asked_from,
        before,
    )


# What "Yes" to sensitive data tells the researcher at once. It does not depend on the deployment:
# whether the data may reach the agent at all is for the governance step.
SENSITIVE_NOTICE = (
    "Please do not paste or upload the sensitive data itself into this conversation. "
    "The governance step will cover how it is handled."
)

# What "No" to a Data Management Plan tells the researcher at once. Writing one is optional in
# Figure 1, so it is never the suggested step, though it comes early in Phase 1; the notice says it
# is still there.
DMP_NOTICE = (
    "Writing a Data Management Plan is optional in this process. You can start one at any time: "
    'choose "Write a Data Management Plan" in the phase tracker, or ask in the conversation.'
)

# The intake's questions, in the order they are asked.
INTAKE: tuple[IntakeQuestion, ...] = (
    IntakeQuestion(
        ENTRY,
        "Where are you with your research data?",
        tuple(IntakeOption(str(e.number), f"{e.text[0].upper()}{e.text[1:]}") for e in ENTRIES),
        tuple(e.number for e in ENTRIES),
    ),
    # Figure 1's decision: "Yes" goes on to review the plan and "No" to create one. Both steps are
    # out of scope, and the answer skips the branch not taken.
    _yes_no(
        "intake.dmp",
        "Do you have a Data Management Plan for this project?",
        (1, 2),
        yes=("setup.dmp-create",),
        no=("setup.dmp-review",),
        notices={NO: DMP_NOTICE},
        before="setup.dmp-create",
    ),
    _yes_no(
        "intake.sensitive",
        "Does the data include personal or otherwise sensitive information?",
        (1, 2),
        no=("governance.sensitive-data-identify", "governance.sensitive-data-handle"),
        notices={YES: SENSITIVE_NOTICE},
        before="governance.sensitive-data-identify",
    ),
    _yes_no(
        "intake.repository-mandated",
        "Has a funder, journal or institution said where the data must go?",
        (1, 2, 3),
        yes=("repository.recommend",),
        no=("repository.mandated",),
        before="repository.mandated",
    ),
)


# The question ids an earlier release asked and this one does not, each with the question that
# replaces it, or None where none does, so that a project log naming one still reads. A question's
# id is stored in every `intake_answered`, so it is never deleted or reused, only retired here
# (docs/specs/projects.md). Never remove an entry.
RETIRED_QUESTIONS: Mapping[str, str | None] = {}


def current_question(question_id: str) -> str | None:
    """The question a stored `question_id` names in this release: itself, the question that
    replaced it if it is retired, or None if it is retired with no successor or unknown here (a
    log written by a later release). Read every question id from a project log through this."""
    if any(q.id == question_id for q in INTAKE):
        return question_id
    return RETIRED_QUESTIONS.get(question_id)


def question(question_id: str) -> IntakeQuestion:
    for q in INTAKE:
        if q.id == question_id:
            return q
    raise KeyError(f"the intake has no question {question_id}")

"""Where a project is in the Blueprint's process flow, derived from its log on every read and never
stored (docs/specs/orchestration.md, docs/specs/projects.md).

Two kinds of event bear on it. Some record what a step produces, and so show the step started or
done: an inventory shows the files described, a repository chosen shows one recommended and
picked, a document's versions show the documentation or the metadata drafted (started) and
approved (done), a validation shows the project validated (done if the last one conforms, started
if not), and a package built shows the deposit finalised. The others are the researcher's own
word: `entry_chosen` names the entry point, and `step_marked` marks a step done, skipped, or open
again, for the many steps nothing else in the log records. An `entry_chosen` may instead be an
orchestrator's model's reading of what the researcher said (`entry_source` "model"), a weaker word
that the researcher's own choice replaces and that is never recorded once they have made one.
What the log produces outranks a mark: a step whose output is approved is done whatever it was
marked.

The intake's answers (`intake_answered`, docs/specs/projects.md, rule 20) are the weakest word: a
"No" marks its question's steps skipped only where the log shows no work on the step and the
researcher has not marked it, even open again. The latest answer to a question counts, so "Yes"
after "No" opens the steps again, and an answer counts only while the entry point is one the
question is asked from (`dd_sdk.intake`).

Nothing here orders the steps or keeps a current one. The order, and the step to suggest next, are
`dd_sdk.process_flow`'s; any step may be done, marked or reopened at any time.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final, Literal

from dd_sdk.intake import question
from dd_sdk.process_flow import (
    OUT_OF_SCOPE,
    PHASES,
    STEPS,
    StepState,
    entry,
    progress,
    suggested_next,
)

ENTRY_CHOSEN: Final = "entry_chosen"
STEP_MARKED: Final = "step_marked"
INTAKE_ANSWERED: Final = "intake_answered"
INTAKE_DISMISSED: Final = "intake_dismissed"
# Who recorded an entry point: the researcher, or an orchestrator's model from what they said. An
# `entry_chosen` with no `entry_source` is the researcher's.
ENTRY_BY_RESEARCHER: Final = "researcher"
ENTRY_BY_MODEL: Final = "model"
type EntrySource = Literal["researcher", "model"]
INVENTORY_ADDED: Final = "inventory_added"
REPOSITORY_CHOSEN: Final = "repository_chosen"
DOCUMENT_VERSION_ADDED: Final = "document_version_added"
DOCUMENT_VERSION_DECIDED: Final = "document_version_decided"
PROJECT_VALIDATED: Final = "project_validated"
PACKAGE_BUILT: Final = "package_built"
VALIDATE_STEP: Final = "deposit.validate"

# What a researcher may mark a step: "open" withdraws an earlier mark.
MARKS: Final = ("done", "skipped", "open")

# The step each event shows done when it is recorded.
DONE_BY_EVENT: Final[Mapping[str, str]] = {
    INVENTORY_ADDED: "preparation.files",
    REPOSITORY_CHOSEN: "repository.recommend",
    PACKAGE_BUILT: "deposit.finalise",
}
# The step each document kind's versions show, by the kind the step needs and the kinds it may
# also hold: started once any is proposed, done once the needed kind has an approved version and
# so has every other kind drafted. A dataset with no table needs no data dictionary, so its README
# alone finishes the documentation.
DOCUMENT_STEPS: Final[Mapping[str, tuple[str, tuple[str, ...]]]] = {
    "preparation.metadata": ("metadata_record", ()),
    "preparation.documentation": ("readme", ("data_dictionary",)),
}

_ORDER = {s.id: i for i, s in enumerate(s for p in PHASES for s in p.steps)}
_RANK: Final[Mapping[str, int]] = {"open": 0, "skipped": 1, "started": 2, "done": 3}


def markable(step_id: str) -> bool:
    """Whether a researcher may mark the step: a step of the flow that is in scope."""
    return step_id in STEPS and step_id not in OUT_OF_SCOPE


def entry_chosen(events: Iterable[Mapping[str, Any]]) -> int | None:
    """The entry point chosen last, or None if none has been."""
    return entry_and_source(events)[0]


def entry_and_source(events: Iterable[Mapping[str, Any]]) -> tuple[int | None, EntrySource | None]:
    """The entry point chosen last and who recorded it, or (None, None) if none has been."""
    chosen = [e for e in events if e["event"] == ENTRY_CHOSEN]
    if not chosen:
        return None, None
    last = chosen[-1]
    source: EntrySource = (
        ENTRY_BY_MODEL if last.get("entry_source") == ENTRY_BY_MODEL else ENTRY_BY_RESEARCHER
    )
    return last["entry"], source


def intake_answers(events: Iterable[Mapping[str, Any]]) -> dict[str, tuple[str, ...]]:
    """The values of the latest answer to each intake question but the entry question, whose
    answer is an `entry_chosen`."""
    return {
        e["question_id"]: tuple(e["answer_values"]) for e in events if e["event"] == INTAKE_ANSWERED
    }


def intake_skips(events: Iterable[Mapping[str, Any]]) -> frozenset[str]:
    """The steps the intake's latest answers mark skipped, counting only the questions asked
    from the entry point chosen last."""
    events = list(events)
    chosen = entry_chosen(events)
    skipped: set[str] = set()
    for question_id, values in intake_answers(events).items():
        asked = question(question_id)
        if asked.asked_at(chosen):
            skipped |= asked.skips(values)
    return frozenset(skipped)


def step_states(events: Iterable[Mapping[str, Any]]) -> dict[str, StepState]:
    """Each step the log shows started, done or skipped, in flow order; an open step is left out.

    The strongest word comes first: work the log shows, then the researcher's own mark, then a
    skip the intake implies."""
    events = list(events)
    produced: dict[str, StepState] = {}
    marked: dict[str, StepState] = {}
    kinds_proposed: set[str] = set()
    kinds_approved: set[str] = set()
    kind_of: dict[str, str] = {}
    for event in events:
        name = event["event"]
        if name in DONE_BY_EVENT:
            produced[DONE_BY_EVENT[name]] = "done"
        elif name == DOCUMENT_VERSION_ADDED:
            kind_of[event["document_id"]] = event["document_kind"]
            kinds_proposed.add(event["document_kind"])
        elif name == DOCUMENT_VERSION_DECIDED and event.get("decision") == "approved":
            kind = kind_of.get(event["document_id"])
            if kind is not None:
                kinds_approved.add(kind)
        elif name == PROJECT_VALIDATED:
            # The last validation decides: one that fails after a pass shows the step begun again.
            produced[VALIDATE_STEP] = "done" if event["conforms"] else "started"
        elif name == STEP_MARKED:
            # An "open" mark is kept: it withdraws an earlier mark and overrides the intake.
            marked[event["step_id"]] = event["mark"]
    for step_id, (needed, also) in DOCUMENT_STEPS.items():
        drafted = {needed, *also} & kinds_proposed
        if needed in kinds_approved and drafted <= kinds_approved:
            produced[step_id] = "done"
        elif drafted:
            produced[step_id] = "started"
    # The further of the two: what the log produced outranks a skip, and a researcher may call a
    # started step done.
    states = {
        step_id: max(
            produced.get(step_id, "open"), marked.get(step_id, "open"), key=_RANK.__getitem__
        )
        for step_id in produced.keys() | marked.keys()
    }
    for step_id in intake_skips(events) - states.keys():
        states[step_id] = "skipped"
    states = {k: v for k, v in states.items() if v != "open"}
    return {k: states[k] for k in sorted(states, key=_ORDER.__getitem__)}


def describe(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The entry point and who recorded it, the step states and the step `suggested_next`
    names, as a project summary carries them and the app's phase tracker shows them."""
    events = list(events)
    (chosen, source), states = entry_and_source(events), step_states(events)
    start = entry(chosen) if chosen is not None else None
    suggested = suggested_next(progress(start, states, []), start)
    return {
        "entry": chosen,
        "entry_source": source,
        "steps": states,
        "suggested": suggested.step.id if suggested is not None else None,
    }

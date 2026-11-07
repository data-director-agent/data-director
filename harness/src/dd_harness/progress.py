"""Where a project is in the Blueprint's process flow, derived from its log on every read and never
stored (docs/specs/orchestration.md, docs/specs/projects.md).

Two kinds of event bear on it. Some record what a step produces, and so show the step started or
done: an inventory shows the files described, a repository chosen shows one recommended and
picked, and a document's versions show the documentation or the metadata drafted (started) and
approved (done). The others are the researcher's own word: `entry_chosen` names the entry point,
and `step_marked` marks a step done, skipped, or open again, for the many steps nothing else in
the log records. What the log produces outranks a mark: a step whose output is approved is done
whatever it was marked.

Nothing here orders the steps or keeps a current one. The order, and the step to suggest next, are
`dd_sdk.process_flow`'s; any step may be done, marked or reopened at any time.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final

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
INVENTORY_ADDED: Final = "inventory_added"
REPOSITORY_CHOSEN: Final = "repository_chosen"
DOCUMENT_VERSION_ADDED: Final = "document_version_added"
DOCUMENT_VERSION_DECIDED: Final = "document_version_decided"

# What a researcher may mark a step: "open" withdraws an earlier mark.
MARKS: Final = ("done", "skipped", "open")

# The step each event shows done when it is recorded.
DONE_BY_EVENT: Final[Mapping[str, str]] = {
    INVENTORY_ADDED: "preparation.files",
    REPOSITORY_CHOSEN: "repository.recommend",
}
# The step each document kind's versions show, by the kind the step needs and the kinds it may
# also hold: started once any is proposed, done once the needed kind has an approved version and
# so has every other kind drafted. A dataset with no table needs no data dictionary, so its README
# alone finishes the documentation. TODO(#19, #202): `deposit.validate` and `deposit.finalise`
# from the validation report and the package, once the log records them.
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
    chosen = [e["entry"] for e in events if e["event"] == ENTRY_CHOSEN]
    return chosen[-1] if chosen else None


def step_states(events: Iterable[Mapping[str, Any]]) -> dict[str, StepState]:
    """Each step the log shows started, done or skipped, in flow order; an open step is left out."""
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
        elif name == STEP_MARKED:
            if event["mark"] == "open":
                marked.pop(event["step_id"], None)
            else:
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
    return {k: states[k] for k in sorted(states, key=_ORDER.__getitem__)}


def describe(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The entry point, the step states and the step `suggested_next` names, as a project
    summary carries them and the app's phase tracker shows them."""
    events = list(events)
    chosen, states = entry_chosen(events), step_states(events)
    start = entry(chosen) if chosen is not None else None
    suggested = suggested_next(progress(start, states, []), start)
    return {
        "entry": chosen,
        "steps": states,
        "suggested": suggested.step.id if suggested is not None else None,
    }

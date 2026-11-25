"""Where a project is in the Blueprint's process flow, derived from its log on every read and never
stored (docs/specs/orchestration.md, docs/specs/projects.md).

Two kinds of event bear on it. Some record what a step produces, and so show the step started or
done: an inventory shows the files described, a repository chosen shows one recommended and
picked, a document's versions show the documentation or the metadata drafted (started) and
approved (done), a project summary proposed or decided shows the project described (started or
done: `setup.project`), a validation shows the project validated (done if the last one conforms,
started if not), and a package built shows the deposit finalised. The others are the
researcher's own word: `entry_chosen` names the entry point, and `step_marked` marks a step done,
skipped, or open again, for the many steps nothing else in the log records. An `entry_chosen` may
instead be an orchestrator's model's reading of what the researcher said (`entry_source`
"model"), a weaker word that the researcher's own choice replaces and that is never recorded once
they have made one.
What the log produces outranks a mark: a step whose output is approved is done whatever it was
marked.

The intake's answers (`intake_answered`, docs/specs/projects.md, rule 20) are the weakest word: a
"No" marks its question's steps skipped only where the log shows no work on the step and the
researcher has not marked it, even open again. The latest answer to a question counts, so "Yes"
after "No" opens the steps again, and an answer counts only while the entry point is one the
question is asked from (`dd_sdk.intake`). A skip also lapses once the log shows its answer's
premise no longer holds: a Data Management Plan written and approved here after "No" to having one
opens the step that reviews it (`REOPENED_BY_DOCUMENT`).

Nothing here orders the steps or keeps a current one. The order, and the step to suggest next, are
`dd_sdk.process_flow`'s; any step may be done, marked or reopened at any time.

The log outlives the release that wrote it, so a step or question it names may since have been
retired. Every such id is read through `dd_sdk.process_flow.current_step` and
`dd_sdk.intake.current_question`: a retired one counts for its successor, or not at all.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from dd_sdk.contract.facts import FactKind
from dd_sdk.intake import ENTRY, INTAKE, current_question, question
from dd_sdk.process_flow import (
    OUT_OF_SCOPE,
    PHASES,
    STEPS,
    StepState,
    current_step,
    entry,
    passed_over,
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
FACT_PROPOSED: Final = "fact_proposed"
FACT_DECIDED: Final = "fact_decided"
# "Describe your project" is started once a summary of the project is proposed and done once a
# person decides one; a rejection leaves it started, since the work has begun.
DESCRIBE_STEP: Final = "setup.project"
DESCRIBED_BY: Final = FactKind.PROJECT_SUMMARY.value
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
#
# A README drafted before the project's inventory, while the data are not collected, plans the
# documentation (`setup.documentation`, #1017): its versions are tallied as `PLANNED_README`, not as
# a README, so they show the Phase 1 step and not the Phase 4 one.
PLANNED_README: Final = "readme:before-collection"
DOCUMENT_STEPS: Final[Mapping[str, tuple[str, tuple[str, ...]]]] = {
    "setup.documentation": (PLANNED_README, ()),
    "preparation.metadata": ("metadata_record", ()),
    "preparation.documentation": ("readme", ("data_dictionary",)),
    "setup.dmp-create": ("dmp", ()),
}
# The steps an intake answer skips that a document of a kind reopens once a version of it is
# approved, since the answer's premise no longer holds: a plan written here after "No" to
# `intake.dmp` is a plan to review (`setup.dmp-review`). A draft alone reopens nothing.
REOPENED_BY_DOCUMENT: Final[Mapping[str, str]] = {"setup.dmp-review": "dmp"}

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
    answer is an `entry_chosen`. An answer to a retired question counts for its successor, or not
    at all."""
    return {
        question_id: tuple(e["answer_values"])
        for e in events
        if e["event"] == INTAKE_ANSWERED
        and (question_id := current_question(e["question_id"])) is not None
    }


def _intake_skippers(events: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Each step the intake's latest answers mark skipped, with the question whose answer does."""
    events = list(events)
    chosen = entry_chosen(events)
    skipped: dict[str, str] = {}
    for question_id, values in intake_answers(events).items():
        asked = question(question_id)
        if asked.asked_at(chosen):
            skipped.update(dict.fromkeys(asked.skips(values), question_id))
    return skipped


def step_states(events: Iterable[Mapping[str, Any]]) -> dict[str, StepState]:
    """Each step the log shows started, done or skipped, in flow order; an open step is left out.

    The strongest word comes first: work the log shows, then the researcher's own mark, then a
    skip the intake implies."""
    return {k: v["state"] for k, v in step_reasons(events).items()}


def step_reasons(events: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Each step `step_states` shows, in flow order, with its state and the word that decided it,
    so the app can say why (docs/specs/app.md, "The phases"). Derived with the states, never
    stored. A reason's `source` is "produced" (the log shows the step's work: `event` names the
    event, and a document step names the `document_id` and `document_kind`), "marked" (the
    researcher marked it) or "intake" (an answer to the intake skipped it: `question_id`). `at` is
    when the deciding event was recorded, where the log says."""
    events = list(events)
    tally = _tally(events)
    _document_steps(tally)
    reasons: dict[str, dict[str, Any]] = {}
    for step_id in tally.produced.keys() | tally.marked.keys():
        # The further of the two: what the log produced outranks a skip, and a researcher may
        # call a started step done. On a tie the log's own work is the reason.
        made, mark = tally.produced.get(step_id, "open"), tally.marked.get(step_id, "open")
        if _RANK[made] >= _RANK[mark] and made != "open":
            reasons[step_id] = _produced(made, tally.produced_by[step_id], tally.kind_of)
        else:
            reasons[step_id] = _reason(mark, "marked", tally.marked_by[step_id])
    reopened = {s for s, kind in REOPENED_BY_DOCUMENT.items() if kind in tally.kinds_approved}
    reasons |= _intake_reasons(events, reasons.keys() | reopened)
    reasons = {k: v for k, v in reasons.items() if v["state"] != "open"}
    return {k: reasons[k] for k in sorted(reasons, key=_ORDER.__getitem__)}


@dataclass
class _Tally:
    """What the log shows of each step, gathered in one pass by `_tally`."""

    produced: dict[str, StepState] = field(default_factory=dict)
    produced_by: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    marked: dict[str, StepState] = field(default_factory=dict)
    marked_by: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    kinds_proposed: set[str] = field(default_factory=set)
    kinds_approved: set[str] = field(default_factory=set)
    kind_of: dict[str, str] = field(default_factory=dict)
    # What each document's latest version is tallied as: its kind, or `PLANNED_README`.
    tallied_as: dict[str, str] = field(default_factory=dict)
    # Whether an inventory has been added yet, so the data exist.
    collected: bool = False
    # The latest event bearing on each document kind: a proposal, or an approval.
    proposed_by: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    approved_by: dict[str, Mapping[str, Any]] = field(default_factory=dict)


def _tally(events: Iterable[Mapping[str, Any]]) -> _Tally:
    """What the log shows of each step: its work, the researcher's marks and the documents."""
    tally = _Tally()
    for event in events:
        name = event["event"]
        if name in DONE_BY_EVENT:
            tally.produced[DONE_BY_EVENT[name]] = "done"
            tally.produced_by[DONE_BY_EVENT[name]] = event
            tally.collected = tally.collected or name == INVENTORY_ADDED
        elif name == DOCUMENT_VERSION_ADDED:
            kind = event["document_kind"]
            tallied = PLANNED_README if kind == "readme" and not tally.collected else kind
            tally.kind_of[event["document_id"]] = kind
            tally.tallied_as[event["document_id"]] = tallied
            tally.kinds_proposed.add(tallied)
            tally.proposed_by[tallied] = event
        elif name == DOCUMENT_VERSION_DECIDED and event.get("decision") == "approved":
            kind = tally.tallied_as.get(event["document_id"])
            if kind is not None:
                tally.kinds_approved.add(kind)
                tally.approved_by[kind] = event
        elif name in (FACT_PROPOSED, FACT_DECIDED):
            _described(tally, event)
        elif name == PROJECT_VALIDATED:
            # The last validation decides: one that fails after a pass shows the step begun again.
            tally.produced[VALIDATE_STEP] = "done" if event["conforms"] else "started"
            tally.produced_by[VALIDATE_STEP] = event
        elif name == STEP_MARKED and (step_id := current_step(event["step_id"])) is not None:
            # An "open" mark is kept: it withdraws an earlier mark and overrides the intake.
            tally.marked[step_id] = event["mark"]
            tally.marked_by[step_id] = event
    return tally


def _described(tally: _Tally, event: Mapping[str, Any]) -> None:
    """Add to `tally` what a proposal of, or decision on, the project's summary shows."""
    if event["fact"].get("fact_kind") != DESCRIBED_BY:
        return
    # A later proposal does not undo a decision; a later decision, whatever it is, replaces one.
    if event["event"] == FACT_PROPOSED and tally.produced.get(DESCRIBE_STEP) == "done":
        return
    decided = event["event"] == FACT_DECIDED and event.get("verdict") != "rejected"
    tally.produced[DESCRIBE_STEP] = "done" if decided else "started"
    tally.produced_by[DESCRIBE_STEP] = event


def _document_steps(tally: _Tally) -> None:
    """Add to `tally` each document step its documents show started or done."""
    for step_id, (needed, also) in DOCUMENT_STEPS.items():
        drafted = {needed, *also} & tally.kinds_proposed
        if needed in tally.kinds_approved and drafted <= tally.kinds_approved:
            tally.produced[step_id] = "done"
            tally.produced_by[step_id] = _latest(tally.approved_by[k] for k in drafted)
        elif drafted:
            tally.produced[step_id] = "started"
            tally.produced_by[step_id] = _latest(tally.proposed_by[k] for k in drafted)


def _intake_reasons(
    events: list[Mapping[str, Any]], decided: Iterable[str]
) -> dict[str, dict[str, Any]]:
    """The steps the intake's answers skip that nothing stronger has decided."""
    decided = set(decided)
    reasons: dict[str, dict[str, Any]] = {}
    for step_id, question_id in _intake_skippers(events).items():
        if step_id in decided:
            continue
        reasons[step_id] = {
            "state": "skipped",
            "source": "intake",
            "event": INTAKE_ANSWERED,
            "question_id": question_id,
        }
        at = _answered_at(events, question_id)
        if at is not None:
            reasons[step_id]["at"] = at
    return reasons


def _latest(events: Iterable[Mapping[str, Any]]) -> Mapping[str, Any]:
    """The event recorded last of `events`, by its `at` where the log gives one."""
    return max(events, key=lambda e: str(e.get("at", "")))


def _reason(state: str, source: str, event: Mapping[str, Any]) -> dict[str, Any]:
    reason: dict[str, Any] = {"state": state, "source": source, "event": event["event"]}
    if "at" in event:
        reason["at"] = event["at"]
    return reason


def _produced(state: str, event: Mapping[str, Any], kind_of: Mapping[str, str]) -> dict[str, Any]:
    reason = _reason(state, "produced", event)
    if "document_id" in event:
        reason["document_id"] = event["document_id"]
        kind = event.get("document_kind") or kind_of.get(event["document_id"])
        if kind is not None:
            reason["document_kind"] = kind
    return reason


def _answered_at(events: Iterable[Mapping[str, Any]], question_id: str) -> str | None:
    answers = [
        e
        for e in events
        if e["event"] == INTAKE_ANSWERED and current_question(e["question_id"]) == question_id
    ]
    return answers[-1].get("at") if answers else None


def decisions(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The intake's decision points as the journey map draws them (§8's diamonds): each question
    but the entry question, in order, with the step it sits before, whether it is asked from the
    project's entry point, and the current answer's values and labels (None while unanswered)."""
    events = list(events)
    chosen, answers = entry_chosen(events), intake_answers(events)
    found = []
    for q in INTAKE:
        if q.id == ENTRY:
            continue
        values = answers.get(q.id)
        labels = {o.value: o.label for o in q.options}
        found.append(
            {
                "question_id": q.id,
                "prompt": q.prompt,
                "before": q.before,
                "asked": q.asked_at(chosen),
                "answer_values": list(values) if values is not None else None,
                "answer_labels": [labels[v] for v in values if v in labels]
                if values is not None
                else None,
            }
        )
    return found


def describe(
    events: Iterable[Mapping[str, Any]], manifest: Iterable[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """The entry point and who recorded it, the step states and the step `suggested_next`
    names, as a project summary carries them and the app's phase tracker shows them, with why
    each step is in its state (`step_reasons`) and the intake's decision points (`decisions`),
    which the journey map draws. `manifest` is the agents the deployment enables, so that the
    suggestion is a step one of them serves where there is one (#1377); the steps it passed over
    for that reason (`passed_over`) let the app say why the suggestion is not the first."""
    events = list(events)
    (chosen, source), reasons = entry_and_source(events), step_reasons(events)
    states = {k: v["state"] for k, v in reasons.items()}
    start = entry(chosen) if chosen is not None else None
    steps = progress(start, states, manifest)
    suggested = suggested_next(steps, start)
    return {
        "entry": chosen,
        "entry_source": source,
        "steps": states,
        "suggested": suggested.step.id if suggested is not None else None,
        "passed_over": [s.step.id for s in passed_over(steps, suggested)],
        "reasons": reasons,
        "decisions": decisions(events),
    }

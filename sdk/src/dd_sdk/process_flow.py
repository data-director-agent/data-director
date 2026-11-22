"""The Blueprint's process flow: three entry points into six phases (§8.1, §8.2, Figures 1 to 6).

Researchers do not always start at the beginning. Entry 1 is before data collection, Entry 2 is
with data collected and being prepared for sharing, and Entry 3 is ready to deposit. Each enters
at its own phase and continues through the same final phases. Each step names the functional
requirements (§7.1) the Blueprint applies at that point, or none.

This is Blueprint data, the same for every agent. Which steps an agent serves is the agent's own
declaration, `AgentSpec.serves`, carried on its manifest entry (docs/specs/orchestration.md); `plan`
joins the two, so an orchestrator keeps no map of agents. An agent names steps, not requirements:
the requirements it bears on follow from its steps' `requirements`. A step's `id` is this
repository's label, not the Blueprint's. Governance as the entry point is deferred to the
Blueprint's v2.0 (Appendix G, comment 1) and is not here.

Where a researcher is in the flow is never stored: the harness derives each step's state (open,
started, done or skipped) from the project log on every turn, and `progress` joins those states
to the plan. Work is not linear, so a step done out of order counts wherever it falls, and the
next step `suggested_next` names is a suggestion an orchestrator offers, never a gate
(docs/specs/orchestration.md).

The phases and steps themselves, with the wording the app shows and which are out of scope, are
in `dd_sdk.flow_phases`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from dd_sdk.flow_phases import PHASES as PHASES
from dd_sdk.flow_phases import Phase as Phase
from dd_sdk.flow_phases import Step as Step


@dataclass(frozen=True)
class Entry:
    number: int
    text: str
    starts_at: int  # the phase the researcher joins at


ENTRIES: tuple[Entry, ...] = (
    Entry(1, "starting a new project, before data collection begins", 1),
    Entry(2, "data already collected, being prepared for sharing", 2),
    Entry(3, "ready to deposit data into a repository", 3),
)

# The functional requirements of §7.1.
REQUIREMENTS: frozenset[str] = frozenset(f"R{n}" for n in range(1, 13))

# The steps' ids, which `AgentSpec.serves` names (docs/specs/orchestration.md).
STEPS: frozenset[str] = frozenset(s.id for p in PHASES for s in p.steps)

# The steps the Blueprint has and this project does not yet do; no agent may serve them.
OUT_OF_SCOPE: frozenset[str] = frozenset(s.id for p in PHASES for s in p.steps if s.out_of_scope)

# The steps a person decides (C2); no agent may serve them either.
PERSON_DECIDES: frozenset[str] = frozenset(
    s.id for p in PHASES for s in p.steps if s.person_decides
)


def requirements_of(step_ids: Iterable[str]) -> tuple[str, ...]:
    """The requirements the steps named apply, in R-number order and without repeats."""
    wanted = set(step_ids)
    found = {r for p in PHASES for s in p.steps if s.id in wanted for r in s.requirements}
    return tuple(sorted(found, key=lambda r: int(r[1:])))


def entry(number: int) -> Entry:
    for e in ENTRIES:
        if e.number == number:
            return e
    raise KeyError(f"the Blueprint has no entry point {number}")


def phases_from(start: Entry) -> tuple[Phase, ...]:
    """The phases a researcher entering at `start` goes through, in order."""
    return tuple(p for p in PHASES if p.number >= start.starts_at)


@dataclass(frozen=True)
class PlannedStep:
    phase: Phase
    step: Step
    agent_ids: tuple[str, ...]  # the agents serving the step


def plan(start: Entry, manifest: Iterable[Mapping[str, Any]]) -> list[PlannedStep]:
    """Each step from `start`, with the agents whose manifest entry `serves` the step's id."""
    serving: dict[str, list[str]] = {}
    for agent in sorted(manifest, key=lambda a: str(a.get("agent_id"))):
        for served in dict.fromkeys(agent.get("serves") or ()):
            serving.setdefault(str(served), []).append(str(agent.get("agent_id")))
    return [
        PlannedStep(phase, step, tuple(serving.get(step.id, ())))
        for phase in phases_from(start)
        for step in phase.steps
    ]


# How far a step has gone, as the project log shows it (docs/specs/orchestration.md).
StepState = Literal["open", "started", "done", "skipped"]
STEP_STATES: tuple[StepState, ...] = ("open", "started", "done", "skipped")


@dataclass(frozen=True)
class ProgressStep:
    phase: Phase
    step: Step
    agent_ids: tuple[str, ...]  # the agents serving the step
    state: StepState


def progress(
    start: Entry | None, states: Mapping[str, str], manifest: Iterable[Mapping[str, Any]]
) -> list[ProgressStep]:
    """Each step from `start` with its state and the agents serving it. A phase before `start` is
    included where one of its steps has started or is done, since work done out of order still
    counts; a skip is no work, so an intake answer that skips a step before `start` does not bring
    its phase back. With no `start`, every phase is included. A step `states` leaves out is open."""
    first = start.starts_at if start is not None else 1
    worked = ("started", "done")
    earlier = {p.number for p in PHASES if any(_state(states.get(s.id)) in worked for s in p.steps)}
    included = {p.number for p in PHASES if p.number >= first} | earlier
    planned = plan(entry(1), manifest)
    return [
        ProgressStep(p.phase, p.step, p.agent_ids, _state(states.get(p.step.id)))
        for p in planned
        if p.phase.number in included
    ]


def _state(value: str | None) -> StepState:
    return next((s for s in STEP_STATES if s == value), "open")


def suggested_next(steps: Iterable[ProgressStep], start: Entry | None) -> ProgressStep | None:
    """The step to suggest next: the first one from `start`'s phase that is neither done nor
    skipped, in scope and not optional; a started step before an open one; and, within the phase
    of the first open step, one an agent serves before one no agent does, so that a researcher is
    not first sent to a step nothing here can help with when the same phase has one it can
    (#1377). The suggestion never leaves that phase for an agent: with none of its steps served,
    as when `steps` were planned from no manifest, it is the first open one, named as having no
    agent. None when all are done.

    With no `start`, where the researcher is is not known, so no open step is suggested: only a
    started one, from any phase, or None. Suggesting the first step of Phase 1 would tell a
    researcher whose data are already collected to plan their collection."""
    first = start.starts_at if start is not None else 1
    candidates = [
        s
        for s in steps
        if s.phase.number >= first
        and s.state in ("open", "started")
        and not s.step.out_of_scope
        and not s.step.optional
    ]
    started = [s for s in candidates if s.state == "started"]
    if start is None:
        return next(iter(started), None)
    phase = candidates[0].phase.number if candidates else None
    served = [s for s in candidates if s.agent_ids and s.phase.number == phase]
    return next(iter(started or served or candidates), None)

"""Watching a run as the conductor makes it: its fixed stages, its checks' reports and the children
it delegates to, for a transport that shows a run's progress (docs/specs/transport.md, the AG-UI
binding).

A watcher only watches. What it is told cannot change a run, and an exception it raises is logged
and dropped, so a broken stream never changes an outcome or loses a stored run.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from dd_harness.grounding import GroundingReport
from dd_harness.sources import SourceReport
from dd_sdk.agent import AgentResult
from dd_sdk.contract import problem as problems
from dd_sdk.contract.models import (
    Envelope,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ProblemDetails,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Step:
    """One of the conductor's fixed stages: `id` is stable and `label` is for people."""

    id: str
    label: str


GATE = Step("gate", "Policy gate")
INPUT = Step("input", "Input check")
AGENT = Step("agent", "Agent")
GROUNDING = Step("grounding", "Grounding check")
SOURCES = Step("sources", "Source check")

# Every run's plan, in the order the stages run. Human review joins it once it is built,
# TODO(#72).
STEPS: tuple[Step, ...] = (GATE, INPUT, AGENT, GROUNDING, SOURCES)


class RunObserver(Protocol):
    """Told what one run is doing, from the conductor's thread, in order: `plan` once, then for each
    stage that runs `step_started` and `step_finished`, with `grounding` and `sources` inside their
    stages. A stage that does not run, such as the agent after a policy refusal, is not told.

    While the agent stage runs, a delegation agent's children are told too, from the threads they
    run on: `child_started` when the conductor admits one, then `child_finished` with its outcome
    status once it is stored, or `child_failed` if the conductor could not make a run of it. A
    child's own stages are not told (docs/specs/app.md, "Run events to the browser")."""

    def plan(self, steps: tuple[Step, ...]) -> None: ...

    def step_started(self, step: Step) -> None: ...

    def step_finished(self, step: Step) -> None: ...

    def grounding(self, report: GroundingReport) -> None: ...

    def sources(self, report: SourceReport) -> None: ...

    def child_started(self, invocation_id: str, agent_id: str) -> None: ...

    def child_finished(self, invocation_id: str, agent_id: str, status: str) -> None: ...

    def child_failed(self, invocation_id: str, agent_id: str, message: str) -> None: ...


class NullObserver:
    """Watches nothing: the observer of a run nobody streams."""

    def plan(self, steps: tuple[Step, ...]) -> None:
        pass

    def step_started(self, step: Step) -> None:
        pass

    def step_finished(self, step: Step) -> None:
        pass

    def grounding(self, report: GroundingReport) -> None:
        pass

    def sources(self, report: SourceReport) -> None:
        pass

    def child_started(self, invocation_id: str, agent_id: str) -> None:
        pass

    def child_finished(self, invocation_id: str, agent_id: str, status: str) -> None:
        pass

    def child_failed(self, invocation_id: str, agent_id: str, message: str) -> None:
        pass


class Watch:
    """The conductor's side of one run's observer and cancel flag. It calls the observer so that
    an exception cannot reach the run, and says whether the caller has cancelled it."""

    def __init__(self, observer: RunObserver | None, cancel: threading.Event | None) -> None:
        self._observer: RunObserver = observer or NullObserver()
        self._cancel = cancel

    def cancelled(self) -> bool:
        """A method, not a property: the answer changes while the run goes on."""
        return self._cancel is not None and self._cancel.is_set()

    def _tell(self, method: str, *args: object) -> None:
        try:
            getattr(self._observer, method)(*args)
        except Exception:  # a watcher never changes a run
            log.exception("run observer %s failed; the run goes on", method)

    def plan(self) -> None:
        self._tell("plan", STEPS)

    def started(self, step: Step) -> None:
        self._tell("step_started", step)

    def finished(self, step: Step) -> None:
        self._tell("step_finished", step)

    def grounding(self, report: GroundingReport) -> None:
        self._tell("grounding", report)

    def sources(self, report: SourceReport) -> None:
        self._tell("sources", report)

    def child(self, request: InvocationRequest, run: Callable[[], Envelope]) -> Envelope:
        """`run()`, the delegated child `request`, told to the observer as it starts and as it
        finishes with its outcome status, or fails if the conductor could not make a run of it."""
        self.child_started(request.invocation_id, request.agent_id)
        try:
            envelope = run()
        except Exception as exc:
            self.child_failed(request.invocation_id, request.agent_id, str(exc))
            raise
        self.child_finished(envelope.invocation_id, envelope.agent_id, envelope.outcome.status)
        return envelope

    def child_started(self, invocation_id: str, agent_id: str) -> None:
        self._tell("child_started", invocation_id, agent_id)

    def child_finished(self, invocation_id: str, agent_id: str, status: str) -> None:
        self._tell("child_finished", invocation_id, agent_id, status)

    def child_failed(self, invocation_id: str, agent_id: str, message: str) -> None:
        self._tell("child_failed", invocation_id, agent_id, message)


def cancelled_result(agent_id: str, *, ran: bool) -> tuple[AgentResult, ProblemDetails]:
    """The result of a run its caller cancelled: failed with `run-cancelled`, nothing kept of what
    the agent answered (docs/specs/transport.md)."""
    detail = (
        f"The run was cancelled while {agent_id} worked; what it answered was discarded."
        if ran
        else f"The run was cancelled before {agent_id} was run."
    )
    return (
        AgentResult(outcome=Outcome(status=OutcomeStatus.FAILED, statement=detail)),
        problems.run_cancelled(detail),
    )

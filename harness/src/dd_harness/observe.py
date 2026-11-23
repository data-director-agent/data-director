"""Watching a run as the conductor makes it: its fixed stages, its checks' reports and the children
it delegates to, for a transport that shows a run's progress (docs/specs/transport.md, the AG-UI
binding).

A watcher only watches. What it is told cannot change a run, and an exception it raises is logged
and dropped, so a broken stream never changes an outcome or loses a stored run.

Whatever a watcher is told is also recorded, one JSON object per call (`StageRecorder`), and the
conductor keeps the records as the run's `stages.jsonl` artifact (docs/specs/storage.md), so a run
can be replayed, and debugged, as the person watching it saw it.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

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
    child's own stages are not told (docs/specs/app.md, "Run events to the browser").

    Each call the agent makes through the tool gateway is told too, from the gateway's thread:
    `tool_started` with the call's id and the tool's gateway name, then `tool_finished` once it has
    answered. Only the name travels: never the call's arguments or what it returned."""

    def plan(self, steps: tuple[Step, ...]) -> None: ...

    def step_started(self, step: Step) -> None: ...

    def step_finished(self, step: Step) -> None: ...

    def grounding(self, report: GroundingReport) -> None: ...

    def sources(self, report: SourceReport) -> None: ...

    def child_started(self, invocation_id: str, agent_id: str) -> None: ...

    def child_finished(self, invocation_id: str, agent_id: str, status: str) -> None: ...

    def child_failed(self, invocation_id: str, agent_id: str, message: str) -> None: ...

    def tool_started(self, call_id: str, name: str) -> None: ...

    def tool_finished(self, call_id: str, name: str, *, ok: bool) -> None: ...


def plan_value(steps: tuple[Step, ...]) -> dict[str, Any]:
    return {"steps": [{"id": step.id, "label": step.label} for step in steps]}


def grounding_value(report: GroundingReport) -> dict[str, Any]:
    return dataclasses.asdict(report)


def sources_value(report: SourceReport) -> dict[str, Any]:
    return {"passed": report.passed, **dataclasses.asdict(report)}


class StageRecorder:
    """A run observer that turns each call into one JSON object, `{"event": <method>, ...}`, and
    hands it to `stage`. It is the one mapping from what the conductor tells to a record: the
    stored `stages.jsonl` and every transport's events are made from these records. A tool call is
    recorded by its gateway name only, never its arguments or what it returned."""

    def stage(self, record: dict[str, Any]) -> None:
        raise NotImplementedError

    def plan(self, steps: tuple[Step, ...]) -> None:
        self.stage({"event": "plan", **plan_value(steps)})

    def step_started(self, step: Step) -> None:
        self.stage({"event": "step_started", "step": step.id})

    def step_finished(self, step: Step) -> None:
        self.stage({"event": "step_finished", "step": step.id})

    def grounding(self, report: GroundingReport) -> None:
        self.stage({"event": "grounding", "report": grounding_value(report)})

    def sources(self, report: SourceReport) -> None:
        self.stage({"event": "sources", "report": sources_value(report)})

    def child_started(self, invocation_id: str, agent_id: str) -> None:
        self.stage({"event": "child_started", "invocation_id": invocation_id, "agent_id": agent_id})

    def child_finished(self, invocation_id: str, agent_id: str, status: str) -> None:
        self.stage(
            {
                "event": "child_finished",
                "invocation_id": invocation_id,
                "agent_id": agent_id,
                "status": str(status),
            }
        )

    def child_failed(self, invocation_id: str, agent_id: str, message: str) -> None:
        self.stage(
            {
                "event": "child_failed",
                "invocation_id": invocation_id,
                "agent_id": agent_id,
                "message": message,
            }
        )

    def tool_started(self, call_id: str, name: str) -> None:
        self.stage({"event": "tool_started", "call_id": call_id, "name": name})

    def tool_finished(self, call_id: str, name: str, *, ok: bool) -> None:
        self.stage({"event": "tool_finished", "call_id": call_id, "name": name, "ok": ok})


class _Kept(StageRecorder):
    """The records of one run, each with the time it was told, in the order told. Children and
    tool calls are told from other threads, so appending takes a lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.records: list[dict[str, Any]] = []

    def stage(self, record: dict[str, Any]) -> None:
        at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self._lock:
            self.records.append({"at": at, **record})


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

    def tool_started(self, call_id: str, name: str) -> None:
        pass

    def tool_finished(self, call_id: str, name: str, *, ok: bool) -> None:
        pass


class Watch:
    """The conductor's side of one run's observer and cancel flag. It calls the observer so that
    an exception cannot reach the run, and says whether the caller has cancelled it."""

    def __init__(self, observer: RunObserver | None, cancel: threading.Event | None) -> None:
        self._observer: RunObserver = observer or NullObserver()
        self._cancel = cancel
        self._kept = _Kept()

    def stages(self) -> list[dict[str, Any]]:
        """What the run was told, as records, in order (`stages.jsonl`)."""
        return list(self._kept.records)

    def cancelled(self) -> bool:
        """A method, not a property: the answer changes while the run goes on."""
        return self._cancel is not None and self._cancel.is_set()

    def _tell(self, method: str, *args: object, **kwargs: object) -> None:
        for name, observer in (("record", self._kept), ("observer", self._observer)):
            try:
                getattr(observer, method)(*args, **kwargs)
            except Exception:  # a watcher, or the record of one, never changes a run
                log.exception("run %s %s failed; the run goes on", name, method)

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

    def tool_started(self, call_id: str, name: str) -> None:
        self._tell("tool_started", call_id, name)

    def tool_finished(self, call_id: str, name: str, *, ok: bool) -> None:
        self._tell("tool_finished", call_id, name, ok=ok)


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

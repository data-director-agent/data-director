"""Watching a run as the conductor makes it: its fixed stages and its checks' reports, for a
transport that shows a run's progress (docs/specs/transport.md, the AG-UI binding).

A watcher only watches. What it is told cannot change a run, and an exception it raises is logged
and dropped, so a broken stream never changes an outcome or loses a stored run.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Protocol

from dd_harness.grounding import GroundingReport
from dd_harness.sources import SourceReport

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
    stages. A stage that does not run, such as the agent after a policy refusal, is not told."""

    def plan(self, steps: tuple[Step, ...]) -> None: ...

    def step_started(self, step: Step) -> None: ...

    def step_finished(self, step: Step) -> None: ...

    def grounding(self, report: GroundingReport) -> None: ...

    def sources(self, report: SourceReport) -> None: ...


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

"""Shared scaffolding for the six stage nodes.

Every stage does the same three things around its actual work: time itself, write a
`StageReport`, and project its result into the run directory. Doing that in one place is what
makes "one entry per pipeline stage with start and end times" (§6.3) a property of the pipeline
rather than something each node remembers to do.

Every node has the same shape, and `merge` is called **after** the `with` block, because that is
when the report exists:

    def profile_node(state, runtime):
        ctx = runtime.context
        with stage(ctx, StageName.PROFILE) as run:
            ...work, setting run.payload / run.counts / run.status...
        return merge(run, profile=run.payload)
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from langgraph.errors import GraphBubbleUp
from pydantic import BaseModel

from standards_advisor.ids import utc_now
from standards_advisor.models.common import (
    PromptRef,
    StageFailure,
    StageName,
    StageReport,
    StageStatus,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from standards_advisor.context import RunContext

#: Stage order, and therefore the numeric prefix on `runs/<run_id>/stages/NN-*.json`.
STAGE_ORDER: tuple[StageName, ...] = (
    StageName.ELICIT,
    StageName.PROFILE,
    StageName.RETRIEVE,
    StageName.RANK,
    StageName.EXPLAIN,
    StageName.CHECK,
    StageName.ASSEMBLE,
)


@dataclass
class StageRun:
    """Mutable scratch space a node fills in while it works."""

    stage: StageName
    status: StageStatus = StageStatus.OK
    counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    prompts: list[PromptRef] = field(default_factory=list)
    model_id: str | None = None
    model_params: dict[str, str] = field(default_factory=dict)
    failures: list[StageFailure] = field(default_factory=list)
    payload: Any = None
    """This stage's output. Written into the stage file and usually returned to the graph."""

    report: StageReport | None = None
    """Set by `stage()` when the block exits. Read via `merge`."""

    def fail(self, kind: str, detail: str) -> None:
        """Record a content-level problem. Never raises — see `errors`."""
        self.failures.append(
            StageFailure(stage=self.stage, kind=kind, detail=detail, at=utc_now().isoformat())
        )

    def note(self, text: str) -> None:
        self.notes.append(text)


@contextmanager
def stage(ctx: RunContext, name: StageName) -> Iterator[StageRun]:
    """Run one stage, then write its report and stage file.

    An unexpected exception is allowed to propagate — those are programmer or configuration
    errors and must not be smuggled into a document as though the run succeeded — but the stage
    file is written first, so the run directory shows where it stopped and why.
    """
    run = StageRun(stage=name)
    started = utc_now().isoformat()
    try:
        yield run
    except GraphBubbleUp:
        # LangGraph's control-flow signals — `interrupt()` pausing for human input, a parent
        # command, a drained graph — all inherit from `Exception`, so without this clause the
        # generic handler below would record a pause as a DEGRADED stage that "raised
        # GraphInterrupt", write a stage file for a stage that has not finished, and then write
        # a second one when the node re-runs on resume. A pause is control flow, not an outcome:
        # no report, no failure, nothing on disk. The resumed pass writes the one true report.
        raise
    except Exception as exc:
        run.note(f"stage raised {type(exc).__name__}: {exc}")
        run.report = _build_report(run, started, StageStatus.DEGRADED)
        _write_stage_file(ctx, name, run)
        raise
    run.report = _build_report(run, started, run.status)
    _write_stage_file(ctx, name, run)


def merge(run: StageRun, **updates: Any) -> dict[str, Any]:
    """Build a node's return value: its own updates, plus the report and any failures."""
    if run.report is None:  # pragma: no cover — a node calling merge inside the with block
        raise RuntimeError("merge() must be called after the stage() block has exited")
    result: dict[str, Any] = dict(updates)
    result["stage_reports"] = [run.report]
    if run.failures:
        result["failures"] = list(run.failures)
    return result


def _build_report(run: StageRun, started: str, status: StageStatus) -> StageReport:
    return StageReport(
        stage=run.stage,
        status=status,
        started_at=started,
        ended_at=utc_now().isoformat(),
        counts=dict(run.counts),
        notes=list(run.notes),
        prompts=list(run.prompts),
        model_id=run.model_id,
        model_params=dict(run.model_params),
    )


def _write_stage_file(ctx: RunContext, name: StageName, run: StageRun) -> None:
    index = STAGE_ORDER.index(name) + 1
    report = run.report.model_dump(mode="json") if run.report is not None else None
    ctx.run_dir.write_stage(
        index,
        name.value,
        {"report": report, "output": _dump(run.payload)},
    )


def _dump(payload: Any) -> Any:
    if payload is None:
        return None
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, list):
        return [_dump(item) for item in payload]
    if isinstance(payload, dict):
        return {key: _dump(value) for key, value in payload.items()}
    return payload

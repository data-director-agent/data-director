"""Running the pipeline once, and writing the run record around it.

Kept out of `cli.py` so a test can drive a whole run without going through argument parsing,
and so a future API or viewer has one function to call rather than a command line to imitate.

§8 adds a second way a run can end: paused, waiting for the researcher to answer the intake
questions. `run_pipeline` returns a `RunResult` with `interrupt` set and no document, and
`resume_pipeline` continues it from the checkpoint. A pause is not a failure and must not read
like one anywhere in the record — hence `exit_status` of `awaiting_input` rather than
`incomplete`, which means "the run never finished" and belongs to a crash.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from langgraph.types import Command

from standards_advisor import __version__
from standards_advisor.checkpointing import checkpointer
from standards_advisor.context import RunContext
from standards_advisor.errors import ConfigError
from standards_advisor.graph import build_graph
from standards_advisor.ids import new_run_id, utc_now
from standards_advisor.intake import load_intake_config
from standards_advisor.models.common import AgentRef, LifecyclePhase, StageStatus
from standards_advisor.models.elicitation import InterruptRequest
from standards_advisor.models.inputs import DatasetInput
from standards_advisor.models.recommendations import RecommendationsDocument
from standards_advisor.prompting import PromptLibrary
from standards_advisor.provenance import (
    ModelRecord,
    ProvenanceHandler,
    RunDirectory,
    RunManifest,
    build_prov_document,
)
from standards_advisor.ranking.weights import load_ranking_config
from standards_advisor.registry import get_registry
from standards_advisor.settings import Settings
from standards_advisor.state import initial_state

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.runnables import RunnableConfig

#: `exit_status` for a run that paused to ask the researcher something (§8). Distinct from
#: `incomplete`, which means the run stopped and is not coming back.
AWAITING_INPUT = "awaiting_input"


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_dir: RunDirectory
    document: RecommendationsDocument | None
    manifest: RunManifest

    interrupt: InterruptRequest | None = None
    """Set when the run paused to ask the researcher something (§8).

    A paused run has no document and is not a failure. `manifest.exit_status` says
    `awaiting_input` rather than `incomplete`, so a pause is distinguishable from a crash, and
    `resume_pipeline` continues it.
    """

    @property
    def awaiting_input(self) -> bool:
        return self.interrupt is not None


def run_pipeline(
    settings: Settings,
    inputs: DatasetInput,
    *,
    model_override: BaseChatModel | None = None,
    use_checkpoints: bool = True,
    run_id: str | None = None,
) -> RunResult:
    """Profile a dataset and produce a recommendations document.

    Returns even when every kind of recommendation was declined — that is a successful run
    (§5.5), and the caller should not have to distinguish it from a failure.

    May also return *paused*, if this is a pre-collection run with no answers supplied. Check
    `RunResult.awaiting_input` and continue with `resume_pipeline`.
    """
    if (
        inputs.phase is LifecyclePhase.PRE_COLLECTION
        and inputs.answers_path is None
        and not use_checkpoints
    ):
        # Refused up front rather than discovered at the pause. Without a checkpoint on disk
        # there is nothing for `resume_pipeline` to read: the in-memory saver dies with the
        # process, so the run would stop at the questions and be unresumable, having done the
        # work of asking them.
        raise ConfigError(
            "a pre_collection run without --answers pauses to ask the researcher, and resuming "
            "needs a checkpoint on disk; drop --no-checkpoints, or supply answers up front"
        )

    run_id = run_id or new_run_id()
    started_at = utc_now().isoformat()

    run_dir = RunDirectory(settings.runs_root, run_id)
    run_dir.write_json("input", inputs.model_dump(mode="json"))

    events = ProvenanceHandler(run_dir)
    ctx = _build_context(settings, run_dir, events, model_override=model_override)

    checkpoint_path = run_dir.checkpoint_path if use_checkpoints else None
    with checkpointer(checkpoint_path) as saver:
        graph = build_graph(saver)
        output = graph.invoke(
            initial_state(run_id, inputs),
            config=_config(run_id, events),
            context=ctx,
            # Persist each stage boundary before the next node starts, rather than at exit.
            # For an auditable pipeline the extra writes are worth it.
            durability="sync",
            # v2 returns a typed `GraphOutput` carrying interrupts separately. v1 folds them
            # into the state dict under a magic key whose access is deprecated — and
            # `filterwarnings = ["error"]` would turn reading it into a test failure.
            version="v2",
        )

    return _finalise(
        settings=settings,
        ctx=ctx,
        events=events,
        run_dir=run_dir,
        run_id=run_id,
        inputs=inputs,
        started_at=started_at,
        final=output.value or {},
        interrupts=output.interrupts,
    )


def resume_pipeline(
    settings: Settings,
    run_id: str,
    answers: dict[str, Any],
    *,
    model_override: BaseChatModel | None = None,
) -> RunResult:
    """Continue a run that paused to ask the researcher something (§8).

    Reads the paused run's own record for the things that must not change across the pause: when
    it started, what it was asked to do, and which versioned configuration was in force. A run
    whose weights or questions changed while a human was thinking is not one run, and the record
    would silently claim it was.
    """
    run_dir = RunDirectory(settings.runs_root, run_id)
    if not run_dir.checkpoint_path.is_file():
        raise ConfigError(
            f"run {run_id} has no checkpoint at {run_dir.checkpoint_path}, so it cannot be "
            "resumed; it was either never paused or was run with --no-checkpoints"
        )

    previous = run_dir.read_json("manifest")
    if not isinstance(previous, dict):
        raise ConfigError(f"run {run_id} has no readable run.json; it cannot be resumed")

    inputs = DatasetInput.model_validate(previous["inputs"])
    started_at = str(previous["started_at"])

    # Counters continue from the event log, not from zero — see `ProvenanceHandler.resumed`.
    events = ProvenanceHandler.resumed(run_dir)
    ctx = _build_context(settings, run_dir, events, model_override=model_override)
    _check_unchanged(previous, ctx, run_id)

    with checkpointer(run_dir.checkpoint_path) as saver:
        graph = build_graph(saver)
        output = graph.invoke(
            # The resume value, not a fresh state: seeding `initial_state` again would discard
            # everything the paused run had already established.
            Command(resume=answers),
            config=_config(run_id, events),
            context=ctx,
            durability="sync",
            version="v2",
        )

    return _finalise(
        settings=settings,
        ctx=ctx,
        events=events,
        run_dir=run_dir,
        run_id=run_id,
        inputs=inputs,
        started_at=started_at,
        final=output.value or {},
        interrupts=output.interrupts,
    )


def _build_context(
    settings: Settings,
    run_dir: RunDirectory,
    events: ProvenanceHandler,
    *,
    model_override: BaseChatModel | None,
) -> RunContext:
    """Assemble the per-run collaborators. Identical for a fresh run and a resumed one."""
    return RunContext(
        registry=get_registry(settings.registry_route),
        registry_route=settings.registry_route,
        prompts=PromptLibrary(settings.prompts_root),
        ranking=load_ranking_config(settings.ranking_config_path()),
        intake=load_intake_config(settings.intake_config_path()),
        run_dir=run_dir,
        events=events,
        agent=AgentRef(identity=settings.agent_identity, version=__version__),
        model_id=settings.model_id,
        model_params={},
        model_override=model_override,
        head_rows=settings.head_rows,
    )


def _config(run_id: str, events: ProvenanceHandler) -> RunnableConfig:
    """The invoke config. `thread_id` is the run id, so a resume finds the same checkpoint."""
    return {
        "configurable": {"thread_id": run_id},
        "callbacks": [events],
        "run_name": f"standards-advisor:{run_id}",
    }


def _check_unchanged(previous: dict[str, Any], ctx: RunContext, run_id: str) -> None:
    """Refuse to resume against configuration that changed while the run was paused.

    The same discipline `PromptLibrary.get` applies to a prompt whose text no longer matches its
    hash, and for the same reason: a run record that names one version of the ranking weights but
    was half-produced under another is worse than no record, because it reads as authoritative.
    """
    recorded_ranking = previous.get("ranking_config")
    if isinstance(recorded_ranking, dict):
        _compare(
            "ranking configuration",
            recorded_ranking.get("version"),
            recorded_ranking.get("sha256"),
            ctx.ranking.version,
            ctx.ranking.sha256,
            run_id,
        )

    # From the manifest, not from `answers.json`: a run pauses *before* the answers are written,
    # so on the only path that can reach here that file does not exist yet and the check would
    # silently never fire. This is also the more important of the two — the researcher has
    # already been shown the questions from the version recorded here.
    recorded_intake = previous.get("intake_config")
    if isinstance(recorded_intake, dict):
        _compare(
            "intake question set",
            recorded_intake.get("version"),
            recorded_intake.get("sha256"),
            ctx.intake.version,
            ctx.intake.sha256,
            run_id,
        )


def _compare(
    label: str,
    recorded_version: object,
    recorded_sha: object,
    current_version: str,
    current_sha: str,
    run_id: str,
) -> None:
    if recorded_version is None or recorded_sha is None:
        return
    if str(recorded_version) != current_version or str(recorded_sha) != current_sha:
        raise ConfigError(
            f"run {run_id} paused under {label} {recorded_version} "
            f"({str(recorded_sha)[:12]}) but {current_version} ({current_sha[:12]}) is in force "
            "now; resuming would produce a run record covering two versions"
        )


def _finalise(
    *,
    settings: Settings,
    ctx: RunContext,
    events: ProvenanceHandler,
    run_dir: RunDirectory,
    run_id: str,
    inputs: DatasetInput,
    started_at: str,
    final: Any,
    interrupts: tuple[Any, ...],
) -> RunResult:
    """Write the run record and build the result. Shared by a fresh run and a resumed one."""
    state = final if isinstance(final, dict) else {}
    document = state.get("document")
    reports = state.get("stage_reports") or []
    failures = state.get("failures") or []
    profile = state.get("profile")

    pending = _interrupt_request(interrupts)

    manifest = RunManifest(
        run_id=run_id,
        started_at=started_at,
        ended_at=utc_now().isoformat(),
        tool_version=__version__,
        agent=ctx.agent,
        inputs=inputs,
        fingerprint=profile.fingerprint if profile else None,
        model=ModelRecord(
            model_id=settings.model_id,
            params=ctx.model_params_as_strings(),
            calls=events.model_calls,
            input_tokens=events.token_totals.get("input_tokens", 0),
            output_tokens=events.token_totals.get("output_tokens", 0),
        ),
        prompts=[ref for report in reports for ref in report.prompts],
        ranking_config=ctx.ranking.ref(),
        intake_config=ctx.intake.ref(),
        registry_snapshot=ctx.registry.snapshot(),
        registry_route=settings.registry_route,
        stages=reports,
        failures=failures,
        exit_status=_exit_status(reports, failures, document, pending),
    )
    run_dir.write_json("manifest", manifest.model_dump(mode="json"))

    prov = build_prov_document(manifest, events.token_totals)
    run_dir.write_json("provenance", prov.to_jsonld())

    return RunResult(
        run_id=run_id,
        run_dir=run_dir,
        document=document,
        manifest=manifest,
        interrupt=pending,
    )


def _interrupt_request(interrupts: tuple[Any, ...]) -> InterruptRequest | None:
    """The pending question set, if the graph paused.

    Tolerant of a payload that will not validate: a pause we cannot describe is still a pause,
    and reporting it as a completed run would be the worse failure.
    """
    for item in interrupts:
        value = getattr(item, "value", None)
        if isinstance(value, dict):
            try:
                return InterruptRequest.model_validate(value)
            except ValueError:
                continue
    return None


def _exit_status(
    reports: list[Any],
    failures: list[Any],
    document: Any,
    pending: InterruptRequest | None,
) -> str:
    """A run that declined everything is `complete`.

    §5.5: "A run that finds no suitable ontology but confidently recommends a date format is a
    *good* run". A run that declines all four is equally valid, and the manifest must not imply
    otherwise — so emptiness never appears here.

    A run that paused is `awaiting_input`, not `incomplete`. Both lack a document, but one is
    waiting for a person and the other has stopped.
    """
    if pending is not None:
        return AWAITING_INPUT
    if document is None:
        return "incomplete"
    if failures or any(report.status is StageStatus.DEGRADED for report in reports):
        return "complete_with_failures"
    return "complete"

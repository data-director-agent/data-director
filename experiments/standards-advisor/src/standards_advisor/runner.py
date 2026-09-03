"""Running the pipeline once, and writing the run record around it.

Kept out of `cli.py` so a test can drive a whole run without going through argument parsing,
and so a future API or viewer has one function to call rather than a command line to imitate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from standards_advisor import __version__
from standards_advisor.checkpointing import checkpointer
from standards_advisor.context import RunContext
from standards_advisor.graph import build_graph
from standards_advisor.ids import new_run_id, utc_now
from standards_advisor.models.common import AgentRef, StageStatus
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


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_dir: RunDirectory
    document: RecommendationsDocument | None
    manifest: RunManifest


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
    """
    run_id = run_id or new_run_id()
    started_at = utc_now().isoformat()

    run_dir = RunDirectory(settings.runs_root, run_id)
    run_dir.write_json("input", inputs.model_dump(mode="json"))

    events = ProvenanceHandler(run_dir)
    ranking = load_ranking_config(settings.ranking_config_path())
    registry = get_registry(settings.registry_route)

    ctx = RunContext(
        registry=registry,
        registry_route=settings.registry_route,
        prompts=PromptLibrary(settings.prompts_root),
        ranking=ranking,
        run_dir=run_dir,
        events=events,
        agent=AgentRef(identity=settings.agent_identity, version=__version__),
        model_id=settings.model_id,
        model_params={},
        model_override=model_override,
        head_rows=settings.head_rows,
    )

    checkpoint_path = run_dir.checkpoint_path if use_checkpoints else None
    with checkpointer(checkpoint_path) as saver:
        graph = build_graph(saver)
        final: dict[str, Any] = graph.invoke(
            initial_state(run_id, inputs),
            config={
                "configurable": {"thread_id": run_id},
                "callbacks": [events],
                "run_name": f"standards-advisor:{run_id}",
            },
            context=ctx,
            # Persist each stage boundary before the next node starts, rather than at exit.
            # For an auditable pipeline the extra writes are worth it.
            durability="sync",
        )

    document = final.get("document")
    reports = final.get("stage_reports") or []
    failures = final.get("failures") or []
    profile = final.get("profile")

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
        ranking_config=ranking.ref(),
        registry_snapshot=registry.snapshot(),
        registry_route=settings.registry_route,
        stages=reports,
        failures=failures,
        exit_status=_exit_status(reports, failures, document),
    )
    run_dir.write_json("manifest", manifest.model_dump(mode="json"))

    prov = build_prov_document(manifest, events.token_totals)
    run_dir.write_json("provenance", prov.to_jsonld())

    return RunResult(run_id=run_id, run_dir=run_dir, document=document, manifest=manifest)


def _exit_status(reports: list[Any], failures: list[Any], document: Any) -> str:
    """A run that declined everything is `complete`.

    §5.5: "A run that finds no suitable ontology but confidently recommends a date format is a
    *good* run". A run that declines all four is equally valid, and the manifest must not imply
    otherwise — so emptiness never appears here.
    """
    if document is None:
        return "incomplete"
    if failures or any(report.status is StageStatus.DEGRADED for report in reports):
        return "complete_with_failures"
    return "complete"

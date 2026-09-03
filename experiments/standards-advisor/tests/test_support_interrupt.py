"""`stage()` must not record a pause as a stage outcome (§8).

`test_resume` observes the consequence of getting this wrong from the outside; this pins the
mechanism, because the reason it is easy to get wrong is not obvious from either end.

LangGraph's control-flow signals — `interrupt()` pausing for input, a parent command, a drained
graph — all inherit from `Exception`, via `GraphBubbleUp`. `stage()`'s generic handler exists to
make sure an unexpected exception still leaves evidence in the run directory, and it would treat
a pause as exactly that: a stage that raised, marked DEGRADED, written to disk unfinished, and
written again when the node re-runs on resume.

Without this test, someone moving an `interrupt()` inside a `with stage(...)` block would
reintroduce that silently — the run would still complete, and only the audit trail would lie.
"""

from __future__ import annotations

import pytest
from langgraph.errors import GraphBubbleUp, GraphInterrupt

from standards_advisor import __version__
from standards_advisor.context import RunContext
from standards_advisor.intake import load_intake_config
from standards_advisor.models.common import AgentRef, StageName, StageStatus
from standards_advisor.nodes.support import stage
from standards_advisor.prompting import PromptLibrary
from standards_advisor.provenance import ProvenanceHandler, RunDirectory
from standards_advisor.ranking.weights import load_ranking_config
from standards_advisor.registry import get_registry
from standards_advisor.settings import Settings


@pytest.fixture
def ctx(settings: Settings, tmp_path) -> RunContext:
    run_dir = RunDirectory(tmp_path / "runs", "test-run")
    return RunContext(
        registry=get_registry("empty"),
        registry_route="empty",
        prompts=PromptLibrary(settings.prompts_root),
        ranking=load_ranking_config(settings.ranking_config_path()),
        intake=load_intake_config(settings.intake_config_path()),
        run_dir=run_dir,
        events=ProvenanceHandler(run_dir),
        agent=AgentRef(identity="urn:dd:agent:test", version=__version__),
        model_id="fake:fake",
    )


def test_a_pause_is_reraised_untouched_and_leaves_nothing_on_disk(ctx: RunContext):
    interrupt = GraphInterrupt(())

    with pytest.raises(GraphInterrupt) as raised, stage(ctx, StageName.ELICIT) as run:
        raise interrupt

    assert raised.value is interrupt, "the signal must reach LangGraph unchanged"
    assert run.report is None, "an unfinished stage has no report to write"
    assert run.status is StageStatus.OK
    assert run.failures == []
    assert list(ctx.run_dir.stages_path.glob("*.json")) == []


def test_the_clause_covers_every_control_flow_signal(ctx: RunContext):
    """Written against `GraphBubbleUp`, not `GraphInterrupt`, on purpose.

    `interrupt()` is the only one this pipeline raises today, but they are all control flow and
    none of them is a stage outcome. Catching the base class means a signal added upstream does
    not quietly start being recorded as a degraded stage.
    """
    assert issubclass(GraphInterrupt, GraphBubbleUp)
    assert issubclass(GraphBubbleUp, Exception), (
        "if this ever stops holding, the clause in support.stage is dead code and the comment "
        "explaining why it exists should go with it"
    )


def test_a_real_exception_is_still_recorded_before_it_propagates(ctx: RunContext):
    """The behaviour the pause clause must not have broken.

    An unexpected exception is a programmer or configuration error, and the run directory has to
    show where it stopped — so the stage file is written first, then the exception re-raised.
    """
    with pytest.raises(ValueError, match="something broke"), stage(ctx, StageName.PROFILE) as run:
        raise ValueError("something broke")

    assert run.report is not None
    assert run.report.status is StageStatus.DEGRADED
    assert any("ValueError" in note for note in run.report.notes)
    assert [path.name for path in ctx.run_dir.stages_path.glob("*.json")] == ["02-profile.json"]

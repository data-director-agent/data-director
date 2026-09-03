"""Pausing for a human, and continuing afterwards (§8).

This is the only place the interrupt path is exercised end to end, and it guards two things that
would otherwise fail silently.

`test_resuming_writes_exactly_one_elicit_report` is the replay regression. LangGraph re-runs an
interrupted node from the top, and `GraphInterrupt` inherits from `Exception` — so without the
`GraphBubbleUp` clause in `support.stage`, the pause would be recorded as a DEGRADED stage that
"raised GraphInterrupt", a stage file would be written for a stage that had not finished, and a
second one written on resume. The run record would show the elicitation failing and then
happening.

`test_the_checkpoint_round_trip_carries_the_state` guards the other one. Before §8 nothing ever
resumed: checkpoints were written for the audit property and never read back, so a model that
could not be deserialised would have gone unnoticed. Now the checkpoint is written by one
process and read by another.
"""

from __future__ import annotations

import json

import pytest

from standards_advisor.errors import ConfigError
from standards_advisor.models.common import LifecyclePhase, StageName, StageStatus
from standards_advisor.models.elicitation import ElicitedContext
from standards_advisor.models.inputs import DatasetInput
from standards_advisor.runner import AWAITING_INPUT, resume_pipeline, run_pipeline
from standards_advisor.settings import Settings

ANSWERS = {
    "subject": ["Soil Science"],
    "entity_scope": ["soil horizons"],
    "formats_planned": ["xlsx"],
}


@pytest.fixture
def paused(settings: Settings, planned_input_asking: DatasetInput):
    return run_pipeline(settings, planned_input_asking)


def test_a_run_with_no_answers_pauses_rather_than_guessing(paused):
    assert paused.awaiting_input
    assert paused.document is None
    assert paused.interrupt is not None
    assert paused.interrupt.intake_version == "intake.v1"
    assert next(question.id for question in paused.interrupt.questions) == "subject"


def test_a_pause_is_not_a_failure(paused):
    """`incomplete` means the run stopped and is not coming back. This one is waiting.

    Both lack a document, so without a distinct status a paused run would be indistinguishable
    from a crashed one in the run record — and `RunManifest.exit_status` is the field a reader
    trusts to tell them what happened.
    """
    assert paused.manifest.exit_status == AWAITING_INPUT
    assert paused.manifest.exit_status != "incomplete"


def test_a_pause_writes_no_stage_files(paused):
    """The `GraphBubbleUp` clause in `support.stage`, observed from outside.

    A stage that has not finished has no report to write. Without the clause there would be a
    `01-elicit.json` here marked degraded.
    """
    assert list(paused.run_dir.stages_path.glob("*.json")) == []
    assert paused.manifest.stages == []
    assert paused.manifest.failures == []


def test_resuming_produces_the_document(settings: Settings, paused):
    resumed = resume_pipeline(settings, paused.run_id, ANSWERS)

    assert resumed.run_id == paused.run_id
    assert not resumed.awaiting_input
    assert resumed.document is not None
    assert resumed.manifest.exit_status != AWAITING_INPUT
    assert len(resumed.document.nothing_found) == 4


def test_resuming_writes_exactly_one_elicit_report(settings: Settings, paused):
    """The replay regression. The node runs twice; the stage is reported once."""
    resumed = resume_pipeline(settings, paused.run_id, ANSWERS)

    elicit_reports = [
        report for report in resumed.manifest.stages if report.stage is StageName.ELICIT
    ]
    assert len(elicit_reports) == 1
    assert elicit_reports[0].status is StageStatus.OK
    assert "raised" not in " ".join(elicit_reports[0].notes)

    files = sorted(path.name for path in resumed.run_dir.stages_path.glob("*.json"))
    assert files[0] == "01-elicit.json"
    assert len(files) == len(list(StageName))


def test_resuming_preserves_when_the_run_started(settings: Settings, paused):
    """Otherwise the run appears to have taken only as long as its tail."""
    resumed = resume_pipeline(settings, paused.run_id, ANSWERS)
    assert resumed.manifest.started_at == paused.manifest.started_at
    assert resumed.manifest.ended_at != paused.manifest.ended_at


def test_the_answers_reach_the_profile(settings: Settings, paused):
    resumed = resume_pipeline(settings, paused.run_id, ANSWERS)
    profile = json.loads(resumed.run_dir.file("profile").read_text(encoding="utf-8"))

    assert [term["term"] for term in profile["subjects"]] == ["Soil Science"]
    assert profile["formats_planned"] == ["xlsx"]
    assert profile["phase"] == "pre_collection"


def test_the_answers_are_recorded_as_interactive(settings: Settings, paused):
    """They were asked for, not supplied up front, and that changes what they evidence."""
    resumed = resume_pipeline(settings, paused.run_id, ANSWERS)
    answers = resumed.run_dir.read_json("answers")

    assert answers["interactive"] is True
    assert answers["asked_at"] and answers["answered_at"]
    assert sum(1 for answer in answers["answers"] if answer["skipped"]) == 5


def test_the_checkpoint_round_trip_carries_the_state(settings: Settings, paused):
    """`ElicitedContext` is written by one process and read by another (§8).

    LangGraph serialises state models with a module-path marker, so moving or renaming this class
    breaks resuming an older checkpoint. `checkpointing.state_types` allowlists our model modules
    explicitly, which both pins that contract and keeps the default "allow anything with a
    warning" behaviour — deprecated upstream — out of the resume path.
    """
    from standards_advisor.checkpointing import checkpointer
    from standards_advisor.graph import build_graph

    resumed = resume_pipeline(settings, paused.run_id, ANSWERS)

    with checkpointer(resumed.run_dir.checkpoint_path) as saver:
        graph = build_graph(saver)
        snapshot = graph.get_state({"configurable": {"thread_id": resumed.run_id}})

    restored = snapshot.values.get("answers")
    assert isinstance(restored, ElicitedContext), (
        f"answers came back from the checkpoint as {type(restored).__name__}"
    )
    assert restored.intake_version == "intake.v1"


def test_a_run_that_cannot_be_resumed_says_so(settings: Settings):
    with pytest.raises(ConfigError, match="no checkpoint"):
        resume_pipeline(settings, "20260101T000000Z-nonesuch", ANSWERS)


def test_asking_without_a_checkpoint_is_refused_up_front(
    settings: Settings, planned_input_asking: DatasetInput
):
    """Refused before the questions are put, not after.

    An in-memory checkpointer dies with the process, so this run would pause and never be
    resumable — having already asked a researcher to answer eight questions.
    """
    with pytest.raises(ConfigError, match="checkpoint on disk"):
        run_pipeline(settings, planned_input_asking, use_checkpoints=False)


def test_answers_supplied_up_front_need_no_checkpoint(settings: Settings, planned_input):
    """The refusal is specific to pausing, not to pre-collection runs in general."""
    result = run_pipeline(settings, planned_input, use_checkpoints=False)
    assert result.document is not None


def test_resuming_under_changed_ranking_weights_is_refused(settings: Settings, paused, tmp_path):
    """A run record covering two versions of the weights would read as authoritative and be wrong.

    The same discipline `PromptLibrary.get` applies to a prompt edited in place: the version and
    hash recorded with a run have to describe what the whole run actually used.
    """
    import shutil

    from standards_advisor.settings import load_settings

    # A project root whose ranking.v1.toml has different content under the same version.
    fake_root = tmp_path / "project"
    shutil.copytree(settings.project_root / "prompts", fake_root / "prompts")
    shutil.copytree(settings.project_root / "config", fake_root / "config")
    (fake_root / "pyproject.toml").write_text("", encoding="utf-8")
    weights = fake_root / "config" / "ranking.v1.toml"
    weights.write_text(
        weights.read_text(encoding="utf-8") + "\n# edited in place\n", encoding="utf-8"
    )

    tampered = load_settings({}, project_root=fake_root, runs_root=settings.runs_root)
    with pytest.raises(ConfigError, match="ranking configuration"):
        resume_pipeline(tampered, paused.run_id, ANSWERS)


def test_resuming_under_a_changed_question_set_is_refused(settings: Settings, paused, tmp_path):
    """The more consequential of the two drift checks.

    The researcher was shown the questions from the version recorded at the pause, so resuming
    under a different set would validate their answers against questions they never saw. Read
    from the manifest rather than `answers.json`, which does not exist yet at a pause.
    """
    import shutil

    from standards_advisor.settings import load_settings

    fake_root = tmp_path / "project"
    shutil.copytree(settings.project_root / "prompts", fake_root / "prompts")
    shutil.copytree(settings.project_root / "config", fake_root / "config")
    (fake_root / "pyproject.toml").write_text("", encoding="utf-8")
    questions = fake_root / "config" / "intake.v1.toml"
    questions.write_text(
        questions.read_text(encoding="utf-8") + "\n# a question added in place\n",
        encoding="utf-8",
    )

    tampered = load_settings({}, project_root=fake_root, runs_root=settings.runs_root)
    with pytest.raises(ConfigError, match="intake question set"):
        resume_pipeline(tampered, paused.run_id, ANSWERS)


def test_a_collected_run_never_pauses(settings: Settings, sample_input: DatasetInput):
    """The existing entry point is untouched: one invoke, no interrupt, no answers."""
    result = run_pipeline(settings, sample_input)
    assert not result.awaiting_input
    assert result.document is not None
    assert result.run_dir.read_json("answers") is None
    assert result.manifest.inputs.phase is LifecyclePhase.COLLECTED

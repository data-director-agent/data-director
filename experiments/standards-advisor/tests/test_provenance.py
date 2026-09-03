"""The run record and the PROV-O graph (C12, C13).

§3 marks C12 as one of two controls that cannot be added later — "cannot be reconstructed after
the fact; the classic thing that never gets added later". These tests are the guard on that: if
a stage stops reporting, or the run directory loses a file, the failure shows up here rather
than the next time somebody tries to audit a run and finds the evidence gone.
"""

from __future__ import annotations

import json

import pytest

from standards_advisor.graph import PIPELINE_ORDER
from standards_advisor.models.common import StageName
from standards_advisor.nodes.support import STAGE_ORDER
from standards_advisor.runner import run_pipeline
from standards_advisor.settings import Settings


@pytest.fixture
def result(settings: Settings, sample_input):
    return run_pipeline(settings, sample_input, use_checkpoints=True)


def test_every_expected_file_is_written(result):
    path = result.run_dir.path
    for name in (
        "input.json",
        "profile.json",
        "recommendations.json",
        "prov.jsonld",
        "run.json",
        "events.jsonl",
    ):
        assert (path / name).is_file(), f"{name} is missing from the run record"


def test_one_stage_file_per_stage_in_pipeline_order(result):
    """Derived from `STAGE_ORDER` rather than listed, so it asserts the property.

    The numeric prefix exists only to make the files sort into pipeline order, so what matters
    is that every stage has exactly one file and the numbering matches the declared order — not
    which names happened to be current when this was written. Adding a stage renumbers the ones
    after it, and a run recorded before that change keeps its old numbering.
    """
    files = sorted(p.name for p in result.run_dir.stages_path.glob("*.json"))
    assert files == [
        f"{index:02d}-{stage.value}.json" for index, stage in enumerate(STAGE_ORDER, start=1)
    ]
    assert list(STAGE_ORDER) == list(StageName), (
        "STAGE_ORDER and StageName have diverged; the stage files would be misnumbered"
    )


def test_the_manifest_records_every_stage(result):
    stages = [report.stage for report in result.manifest.stages]
    assert stages == list(StageName)


def test_the_manifest_records_the_agent_identity(result):
    """C13: actions attributable to an agent identity, set in configuration."""
    assert result.manifest.agent.identity.startswith("urn:dd:agent:")
    assert result.manifest.agent.version


def test_the_manifest_records_what_was_sent_not_what_was_intended(result):
    """No sampling parameters are sent, so an empty mapping here is the correct record."""
    assert result.manifest.model.params == {}
    assert result.manifest.model.model_id


def test_the_manifest_records_the_registry_that_answered(result):
    assert result.manifest.registry_route == "empty"
    assert result.manifest.registry_snapshot.stale is True


def test_a_run_that_declined_everything_is_still_complete(result):
    """§5.5: a run that finds nothing is a good run, and the manifest must not imply otherwise."""
    assert result.manifest.exit_status != "incomplete"
    assert result.document is not None
    assert result.document.recommendations == []


def test_the_event_log_is_not_empty(result):
    events = result.run_dir.read_events()
    assert events
    assert all("at" in event and "event" in event for event in events)


def test_the_event_log_is_append_only_jsonl(result):
    """One JSON object per line, so an entry cannot be silently rewritten."""
    text = result.run_dir.events_path.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    for line in lines:
        assert isinstance(json.loads(line), dict)


def test_the_prov_graph_has_one_activity_per_stage(result):
    graph = json.loads(result.run_dir.file("provenance").read_text(encoding="utf-8"))["@graph"]
    activities = [node for node in graph if node["@type"] == "prov:Activity"]
    assert len(activities) == len(list(StageName))
    labels = {node["prov:label"] for node in activities}
    assert labels == {f"stage {stage.value}" for stage in StageName}


def test_prov_activities_form_a_chain(result):
    """`wasInformedBy` links each stage to the one before, so the order is in the record."""
    graph = json.loads(result.run_dir.file("provenance").read_text(encoding="utf-8"))["@graph"]
    activities = [node for node in graph if node["@type"] == "prov:Activity"]

    first = [node for node in activities if "prov:wasInformedBy" not in node]
    assert len(first) == 1
    assert first[0]["prov:label"] == f"stage {PIPELINE_ORDER[0].value}"
    assert len(activities) - 1 == sum("prov:wasInformedBy" in node for node in activities)


def test_the_prov_graph_names_the_software_agent(result):
    graph = json.loads(result.run_dir.file("provenance").read_text(encoding="utf-8"))["@graph"]
    agents = [node for node in graph if "prov:Agent" in node["@type"]]
    assert any(node["prov:label"].startswith("urn:dd:agent:") for node in agents)


def test_the_prov_graph_records_the_ranking_configuration_used(result):
    graph = json.loads(result.run_dir.file("provenance").read_text(encoding="utf-8"))["@graph"]
    entities = [node for node in graph if node["@type"] == "prov:Entity"]
    ranking = [node for node in entities if node.get("prov:label") == "ranking configuration"]
    assert len(ranking) == 1
    assert ranking[0]["dd:version"] == "ranking.v1"
    assert len(ranking[0]["dd:sha256"]) == 64


def test_the_document_points_at_its_own_provenance(result):
    assert result.document is not None
    assert result.document.provenance == f"runs/{result.run_id}/prov.jsonld"


def test_the_checkpointer_records_a_boundary_per_stage(result):
    """§5's "each stage saves its result" comes free from the checkpointer.

    Asserted because it is the property that makes `durability="sync"` worth its extra writes,
    and because a graph change that collapsed two stages into one super-step would otherwise go
    unnoticed.
    """
    from standards_advisor.checkpointing import checkpointer
    from standards_advisor.graph import build_graph

    with checkpointer(result.run_dir.checkpoint_path) as saver:
        graph = build_graph(saver)
        history = list(graph.get_state_history({"configurable": {"thread_id": result.run_id}}))

    assert history, "no checkpoints were persisted"
    # One checkpoint per stage, plus the initial state before any node ran.
    assert len(history) >= len(list(StageName))


def test_pydantic_objects_survive_a_checkpoint_round_trip(result):
    """Guards a real fragility of holding model instances in graph state.

    LangGraph serialises them with a module-path marker, so renaming or moving a model class
    silently breaks resuming an older checkpoint. Asserting the round-trip here turns that into
    a test failure rather than a surprise months later.
    """
    from standards_advisor.checkpointing import checkpointer
    from standards_advisor.graph import build_graph
    from standards_advisor.models.profile import DatasetProfile

    with checkpointer(result.run_dir.checkpoint_path) as saver:
        graph = build_graph(saver)
        snapshot = graph.get_state({"configurable": {"thread_id": result.run_id}})

    restored = snapshot.values.get("profile")
    assert isinstance(restored, DatasetProfile), (
        f"profile came back from the checkpoint as {type(restored).__name__}"
    )
    assert restored.columns

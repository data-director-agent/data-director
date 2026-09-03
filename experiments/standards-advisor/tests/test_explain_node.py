"""The explain stage and the model seam, exercised with a fake registry and a fake model.

Nothing on the v0.1 sample path calls a model, so without these tests the seam would be
untested until a registry route arrived — and by then the failure would be tangled up with
whatever the registry was doing. Sockets are disabled for the suite, so a real call fails rather
than escaping.

The important assertion is not the happy path but `test_a_malformed_response_is_recorded_not
_raised`: §5.5 treats bad output as a content outcome, and a stage that raised there would
destroy the audit trail at the point where it is most informative.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.runtime import Runtime

from standards_advisor import __version__
from standards_advisor.context import RunContext
from standards_advisor.intake import load_intake_config
from standards_advisor.models.common import (
    AgentRef,
    Derivation,
    LifecyclePhase,
    RecommendationKind,
)
from standards_advisor.models.inputs import DatasetInput
from standards_advisor.models.profile import (
    ColumnProfile,
    ColumnType,
    ContentFingerprint,
    DatasetProfile,
    SourceRef,
)
from standards_advisor.nodes.explain import _profile_digest, explain_node
from standards_advisor.nodes.profile import profile_node
from standards_advisor.nodes.rank import rank_node
from standards_advisor.nodes.retrieve import retrieve_node
from standards_advisor.prompting import PromptLibrary
from standards_advisor.provenance import ProvenanceHandler, RunDirectory
from standards_advisor.ranking.weights import load_ranking_config
from standards_advisor.settings import Settings
from standards_advisor.state import initial_state
from tests.fakes import FakeRegistry, make_record, scripted_model

RECORD_ID = "FAIRsharing.fj07xj"


def _context(settings: Settings, tmp_path: Path, registry, model) -> RunContext:
    run_dir = RunDirectory(tmp_path / "runs", "test-run")
    return RunContext(
        registry=registry,
        registry_route="fake",
        prompts=PromptLibrary(settings.prompts_root),
        ranking=load_ranking_config(settings.ranking_config_path()),
        intake=load_intake_config(settings.intake_config_path()),
        run_dir=run_dir,
        events=ProvenanceHandler(run_dir),
        agent=AgentRef(identity="urn:dd:agent:test", version=__version__),
        model_id="fake:fake",
        model_override=model,
        head_rows=50,
    )


def _stocked_registry() -> FakeRegistry:
    return FakeRegistry(
        {
            RecommendationKind.CONTROLLED_VOCABULARY_LINKAGE.value: [
                make_record(
                    RECORD_ID,
                    "A Soil Horizon Vocabulary",
                    subtype="taxonomy",
                    fields={"recommended_by": "40 data policies"},
                )
            ]
        }
    )


def _run_to_explain(settings: Settings, tmp_path: Path, sample_input: DatasetInput, model):
    """Drive profile → retrieve → rank, then return the state and context for explain."""
    ctx = _context(settings, tmp_path, _stocked_registry(), model)
    runtime = Runtime(context=ctx)
    state = initial_state("test-run", sample_input)

    for node in (profile_node, retrieve_node, rank_node):
        state.update(node(state, runtime))  # type: ignore[typeddict-item]
    return state, ctx, runtime


def test_a_well_formed_response_becomes_an_explanation(settings, tmp_path, sample_input):
    model = scripted_model(
        [
            {
                "explanations": [
                    {
                        "registry_id": RECORD_ID,
                        "reason": "The soil_horizon column holds three horizon codes.",
                        "target_field": "soil_horizon",
                        "caveats": ["Covers horizons only"],
                        "evidence": [
                            {
                                "statement": "Recommended by 40 data policies",
                                "record": RECORD_ID,
                                "field": "recommended_by",
                            }
                        ],
                        "confidence": 0.84,
                    }
                ]
            }
        ]
    )
    state, _ctx, runtime = _run_to_explain(settings, tmp_path, sample_input, model)
    update = explain_node(state, runtime)

    explanations = update["explanations"]
    assert len(explanations) == 1
    assert explanations[0].registry_id == RECORD_ID
    assert explanations[0].target.field == "soil_horizon"
    assert explanations[0].confidence == pytest.approx(0.84)
    assert explanations[0].kind is RecommendationKind.CONTROLLED_VOCABULARY_LINKAGE


def test_the_prompt_version_and_hash_are_recorded(settings, tmp_path, sample_input):
    """§5.4's "recorded with each run" — and the text is copied into the run directory too,
    so reading an old run does not require git archaeology."""
    model = scripted_model([{"explanations": []}])
    state, ctx, runtime = _run_to_explain(settings, tmp_path, sample_input, model)
    update = explain_node(state, runtime)

    report = update["stage_reports"][0]
    assert len(report.prompts) == 1
    assert report.prompts[0].name == "explain"
    assert report.prompts[0].version == "v1"
    assert len(report.prompts[0].sha256) == 64
    assert (ctx.run_dir.prompts_path / "explain.v1.md").is_file()


def test_a_malformed_response_is_recorded_not_raised(settings, tmp_path, sample_input):
    """A parse failure is a content outcome (§5.5), so the run continues and reports it."""
    model = scripted_model(["this is not JSON at all"])
    state, _ctx, runtime = _run_to_explain(settings, tmp_path, sample_input, model)

    update = explain_node(state, runtime)

    assert update["explanations"] == []
    assert any(failure.kind == "explain_unparsed" for failure in update["failures"])
    assert update["stage_reports"][0].status == "degraded"


def test_a_response_naming_an_unknown_candidate_is_dropped(settings, tmp_path, sample_input):
    """The cheap local version of the grounding check.

    The non-negotiable one runs in `check` over the whole output; this one exists because a
    draft naming an identifier we never sent cannot be matched to a kind or a target at all.
    """
    model = scripted_model(
        [
            {
                "explanations": [
                    {
                        "registry_id": "FAIRsharing.invented",
                        "reason": "A standard I have heard of.",
                        "confidence": 0.99,
                    }
                ]
            }
        ]
    )
    state, _ctx, runtime = _run_to_explain(settings, tmp_path, sample_input, model)
    update = explain_node(state, runtime)

    assert update["explanations"] == []
    assert any(failure.kind == "explain_unknown_candidate" for failure in update["failures"])


def test_no_model_is_called_when_there_are_no_candidates(settings, tmp_path, sample_input):
    """The v0.1 path. A fake with no scripted replies would raise if it were invoked."""
    ctx = _context(settings, tmp_path, FakeRegistry(), scripted_model([]))
    runtime = Runtime(context=ctx)
    state = initial_state("test-run", sample_input)
    for node in (profile_node, retrieve_node, rank_node):
        state.update(node(state, runtime))  # type: ignore[typeddict-item]

    update = explain_node(state, runtime)
    assert update["explanations"] == []
    assert update["stage_reports"][0].status == "empty"
    assert ctx.events.model_calls == 0


def test_sample_values_are_never_put_in_the_prompt(settings, tmp_path, sample_input):
    """§1.4 — only names, inferred types and counts may reach a model.

    The constraint belongs in the code that builds the prompt rather than in a reviewer's
    memory, so it is asserted against the rendered text.
    """
    ctx = _context(settings, tmp_path, _stocked_registry(), scripted_model([]))
    runtime = Runtime(context=ctx)
    state = initial_state("test-run", sample_input)
    state.update(profile_node(state, runtime))  # type: ignore[typeddict-item]

    profile = state["profile"]
    assert profile is not None
    digest = _profile_digest(profile)

    # Values that exist in the CSV and must not appear in what is sent to a model.
    for value in ("PDS-2024-001", "0000-0002-1825-0097", "53.3421", "Waterlogged"):
        assert value not in digest, f"{value!r} leaked into the model prompt"

    # Metadata that should be there.
    assert "soil_horizon" in digest
    assert "categorical" in digest


def test_declared_permitted_values_reach_the_prompt_but_observed_values_do_not(settings, tmp_path):
    """§1.4 as amended by §8, and the only mechanical guard on the amended boundary.

    The line is **declared schema versus observed data**, not "values are secret". A codebook
    entry is a statement the researcher wrote about what may be recorded, and it is exactly what
    R3.1 needs in order to match a vocabulary before any data exists. An `example_values` entry
    is an observation read out of a real file, and no amount of usefulness makes it metadata.

    The two live in separate fields precisely so this test can be written: one profile, one
    column, both fields populated, and the digest has to contain one and not the other.
    """
    profile = DatasetProfile(
        profile_id="test-profile",
        fingerprint=ContentFingerprint(digest="0" * 64, total_bytes=0, files_hashed=0),
        source=SourceRef(kind="planned_documentation"),
        profiled_at="2026-09-03T00:00:00+00:00",
        profiler_version=__version__,
        phase=LifecyclePhase.PRE_COLLECTION,
        columns=[
            ColumnProfile(
                name="land_use",
                position=0,
                file="dictionary.json",
                inferred_type=ColumnType.CATEGORICAL,
                type_derivation=Derivation.DECLARED_IN_DATA_DICTIONARY,
                description="How the plot is managed.",
                permitted_values=["grazed", "ungrazed", "restored"],
                example_values=["SECRET-OBSERVED-VALUE"],
            )
        ],
    )

    digest = _profile_digest(profile)

    assert "grazed" in digest
    assert "restored" in digest
    assert "How the plot is managed." in digest
    assert "SECRET-OBSERVED-VALUE" not in digest, "an observed value leaked into the prompt"


def test_a_planned_column_with_no_counts_does_not_break_the_digest(settings):
    """`blank_proportion` is `None` pre-collection, and it is formatted as a percentage.

    A format spec is not type-checked, so mypy would not have caught this — only a run would,
    and only on the pre-collection path.
    """
    profile = DatasetProfile(
        profile_id="test-profile",
        fingerprint=ContentFingerprint(digest="0" * 64, total_bytes=0, files_hashed=0),
        source=SourceRef(kind="planned_documentation"),
        profiled_at="2026-09-03T00:00:00+00:00",
        profiler_version=__version__,
        phase=LifecyclePhase.PRE_COLLECTION,
        columns=[
            ColumnProfile(
                name="ph",
                position=0,
                file="dictionary.json",
                inferred_type=ColumnType.NUMBER,
                type_derivation=Derivation.DECLARED_IN_DATA_DICTIONARY,
            )
        ],
    )

    digest = _profile_digest(profile)
    assert "ph" in digest
    assert "None" not in digest, "a missing count must read as '-', not as the word None"

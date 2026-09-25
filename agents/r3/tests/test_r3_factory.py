"""R3's factory, specification and manifest entry."""

from __future__ import annotations

from pathlib import Path

import pytest

from dd_agent_r3 import factory
from dd_agent_r3.agent import R3Agent
from dd_agent_r3.explain import AnthropicExplainer, TemplateExplainer
from dd_agent_r3.fairsharing.live import LiveBackend
from dd_agent_r3.fairsharing.snapshot import DEFAULT_SNAPSHOT, SnapshotBackend
from dd_agent_r3.testing import make_conductor
from dd_sdk.agent import describe, spec_from_description
from dd_sdk.contract.models import (
    DatasetProfile,
    GroundingMode,
    InvocationRequest,
    OutcomeStatus,
    Recommendations,
)


def test_build_defaults_to_the_committed_snapshot_and_the_template_explainer() -> None:
    agent = factory.build({})
    assert isinstance(agent.retrieval, SnapshotBackend)
    assert agent.retrieval.path == DEFAULT_SNAPSHOT
    assert agent.fallback is None
    assert isinstance(agent.explainer, TemplateExplainer)


def test_live_retrieval_falls_back_to_the_configured_snapshot(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.jsonl"
    agent = factory.build({"DD_R3_RETRIEVAL": "live", "DD_SNAPSHOT_PATH": str(snapshot)})
    assert isinstance(agent.retrieval, LiveBackend)
    assert isinstance(agent.fallback, SnapshotBackend) and agent.fallback.path == snapshot


def test_the_anthropic_explainer_takes_the_configured_model() -> None:
    pytest.importorskip("anthropic")
    agent = factory.build(
        {"DD_R3_EXPLAINER": "anthropic", "DD_MODEL_ID": "m-test", "ANTHROPIC_API_KEY": "unused"}
    )
    assert isinstance(agent.explainer, AnthropicExplainer)
    assert agent.explainer.model_id == "m-test"


@pytest.mark.parametrize("variable", ["DD_R3_RETRIEVAL", "DD_R3_EXPLAINER"])
def test_an_unknown_setting_is_a_configuration_error(variable: str) -> None:
    with pytest.raises(ValueError, match=variable):
        factory.build({variable: "carrier-pigeon"})


@pytest.mark.requirement("DD-REGISTRY", "DD-GROUNDING-MODE")
def test_the_spec_round_trips_through_the_manifest() -> None:
    spec = spec_from_description(describe(R3Agent.spec))
    assert spec.agent_id == "r3.standards-advisor"
    assert spec.accepts == (DatasetProfile,)
    assert spec.grounding_mode == GroundingMode.RETRIEVAL
    assert spec.payload_type is Recommendations
    assert spec.uischema is not None and "items" in spec.uischema


@pytest.mark.requirement("DD-INPUT-ACCEPTS")
def test_an_input_class_it_did_not_declare_is_refused(runs_dir: Path) -> None:
    from workbench.testing import claim

    env = make_conductor(runs_dir, crate=False).invoke(
        InvocationRequest(
            agent_id="r3.standards-advisor", policy_bundle_ref="profile:default", input=claim()
        )
    )
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith("/input-not-accepted")

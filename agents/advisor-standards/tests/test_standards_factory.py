"""The standards advisor's factory, specification and manifest entry."""

from __future__ import annotations

from pathlib import Path

import pytest

import dd_agent_advisor_standards
from dd_agent_advisor_standards import factory
from dd_agent_advisor_standards.advise import ModelAdvisor
from dd_agent_advisor_standards.agent import StandardsAgent
from dd_agent_advisor_standards.classes import DatasetProfile, Recommendations
from dd_agent_advisor_standards.explain import TemplateExplainer
from dd_agent_advisor_standards.fairsharing.live import LiveBackend
from dd_agent_advisor_standards.fairsharing.snapshot import DEFAULT_SNAPSHOT, SnapshotBackend
from dd_agent_advisor_standards.testing import make_conductor
from dd_sdk.agent import ModelUse, describe, spec_from_description
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import GroundingMode, InvocationRequest, OutcomeStatus
from dd_sdk.credentials import ConfigError
from dd_sdk.schema import gen


def test_build_defaults_to_the_committed_snapshot() -> None:
    agent = factory.build({"DD_STANDARDS_EXPLAINER": "template"})
    assert isinstance(agent.retrieval, SnapshotBackend)
    assert agent.retrieval.path == DEFAULT_SNAPSHOT
    assert agent.fallback is None
    assert isinstance(agent.explainer, TemplateExplainer)


def test_live_retrieval_falls_back_to_the_configured_snapshot(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.jsonl"
    agent = factory.build(
        {
            "DD_STANDARDS_RETRIEVAL": "live",
            "DD_SNAPSHOT_PATH": str(snapshot),
            "DD_STANDARDS_EXPLAINER": "template",
        }
    )
    assert isinstance(agent.retrieval, LiveBackend)
    assert isinstance(agent.fallback, SnapshotBackend) and agent.fallback.path == snapshot


def test_the_anthropic_explainer_takes_the_configured_model() -> None:
    pytest.importorskip("anthropic")
    agent = factory.build(
        {
            "DD_STANDARDS_EXPLAINER": "anthropic",
            "DD_MODEL_ID": "m-test",
            "ANTHROPIC_API_KEY": "unused",
        }
    )
    assert isinstance(agent.explainer, ModelAdvisor)
    assert agent.explainer.model_id == "m-test"
    assert agent.spec.models == (ModelUse("anthropic", "m-test", "hosted", True),)
    assert StandardsAgent.spec.models == ()


def test_the_template_explainer_declares_no_model() -> None:
    assert factory.build({"DD_STANDARDS_EXPLAINER": "template"}).spec.models == ()


def test_the_model_is_on_by_default_and_says_how_to_turn_it_off() -> None:
    with pytest.raises(ConfigError, match="DD_STANDARDS_EXPLAINER=template"):
        factory.build({})


def test_the_model_is_on_by_default_with_a_key() -> None:
    pytest.importorskip("anthropic")
    agent = factory.build({"ANTHROPIC_API_KEY": "unused"})
    assert isinstance(agent.explainer, ModelAdvisor)
    assert agent.explainer.max_lookups == factory.DEFAULT_MAX_LOOKUPS


@pytest.mark.parametrize(("raw", "expected"), [("0", 0), ("7", 7)])
def test_the_search_budget_is_configured(raw: str, expected: int) -> None:
    pytest.importorskip("anthropic")
    agent = factory.build({"ANTHROPIC_API_KEY": "unused", "DD_STANDARDS_MAX_LOOKUPS": raw})
    assert isinstance(agent.explainer, ModelAdvisor)
    assert agent.explainer.max_lookups == expected


@pytest.mark.parametrize("raw", ["-1", "31", "many"])
def test_an_unusable_search_budget_stops_at_start_up(raw: str) -> None:
    pytest.importorskip("anthropic")
    with pytest.raises(ConfigError, match="DD_STANDARDS_MAX_LOOKUPS"):
        factory.build({"ANTHROPIC_API_KEY": "unused", "DD_STANDARDS_MAX_LOOKUPS": raw})


def test_the_anthropic_explainer_without_a_key_stops_at_start_up() -> None:
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        factory.build({"DD_STANDARDS_EXPLAINER": "anthropic"})


@pytest.mark.parametrize("variable", ["DD_STANDARDS_RETRIEVAL", "DD_STANDARDS_EXPLAINER"])
def test_an_unknown_setting_is_a_configuration_error(variable: str) -> None:
    with pytest.raises(ConfigError, match=variable):
        factory.build({variable: "carrier-pigeon"})


@pytest.mark.requirement("DD-REGISTRY", "DD-GROUNDING-MODE")
def test_the_spec_round_trips_through_the_manifest() -> None:
    spec = spec_from_description(describe(StandardsAgent.spec))
    assert spec.agent_id == "advisor.standards"
    assert spec.accepts == (ClassSchema.of(DatasetProfile),)
    assert spec.grounding_mode == GroundingMode.RETRIEVAL
    assert spec.payload == ClassSchema.of(Recommendations)
    assert spec.derivations == StandardsAgent.spec.derivations
    assert spec.derivations["items.rationale"].recorded_in == "rationale_derivation"


@pytest.mark.requirement("DD-INPUT-ACCEPTS")
def test_an_input_class_it_did_not_declare_is_refused(runs_dir: Path) -> None:
    from dd_harness.testing import TEST_PRINCIPAL, claim

    env = make_conductor(runs_dir, crate=False).invoke(
        InvocationRequest(agent_id="advisor.standards", input=claim()), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith("/input-not-accepted")


def test_its_classes_are_generated_from_its_own_linkml() -> None:
    source = Path(dd_agent_advisor_standards.__file__).parent / "schema" / "standards.yaml"
    assert gen.stale(source) == [], f"run `uv run dd-gen-schema {source}`"


@pytest.mark.parametrize(
    ("settings", "declared"),
    [
        (
            {"DD_MODEL_PROVIDER": "openai", "DD_MODEL_ID": "m-1", "OPENAI_API_KEY": "k"},
            ("openai", "m-1", "hosted"),
        ),
        (
            {
                "DD_MODEL_PROVIDER": "openai-compatible",
                "DD_MODEL_ID": "llama",
                "DD_MODEL_BASE_URL": "http://localhost:11434/v1",
            },
            ("localhost:11434", "llama", "local"),
        ),
    ],
)
def test_the_model_can_come_from_another_provider(
    settings: dict[str, str], declared: tuple[str, str, str]
) -> None:
    pytest.importorskip("openai")
    agent = factory.build({"DD_STANDARDS_EXPLAINER": "model", **settings})
    assert [(m.provider, m.model, m.hosting) for m in agent.spec.models] == [declared]


def test_the_older_anthropic_setting_names_only_anthropic() -> None:
    with pytest.raises(ConfigError):
        factory.build(
            {
                "DD_STANDARDS_EXPLAINER": "anthropic",
                "DD_MODEL_PROVIDER": "openai",
                "DD_MODEL_ID": "m-1",
                "OPENAI_API_KEY": "k",
            }
        )

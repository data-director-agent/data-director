"""The orchestrator's configuration: its model is declared, and a bad setting stops it at
start-up (docs/specs/policy-and-identity.md)."""

from __future__ import annotations

import pytest

from dd_agent_orchestrator_model import factory
from dd_agent_orchestrator_model.agent import DEFAULT_MODEL
from dd_agent_orchestrator_model.title import DEFAULT_TITLE_MODEL
from dd_sdk.agent import ModelUse
from dd_sdk.credentials import ConfigError

KEY = {"ANTHROPIC_API_KEY": "sk-ant-test"}
OPENAI = {"DD_MODEL_PROVIDER": "openai", "DD_MODEL_ID": "gpt-test", "OPENAI_API_KEY": "sk-test"}
LOCAL = {
    "DD_MODEL_PROVIDER": "openai-compatible",
    "DD_MODEL_ID": "llama-test",
    "DD_MODEL_BASE_URL": "http://localhost:11434/v1",
}


def test_the_spec_declares_the_models_it_calls() -> None:
    built = factory.build(KEY)
    assert built.spec.models == (
        ModelUse("anthropic", DEFAULT_MODEL, "hosted"),
        ModelUse("anthropic", DEFAULT_TITLE_MODEL, "hosted"),
    )
    other = factory.build(
        {**KEY, "DD_MODEL_ID": "claude-opus-5-5", "DD_TITLE_MODEL_ID": "claude-opus-5-5"}
    )
    assert other.spec.models == (ModelUse("anthropic", "claude-opus-5-5", "hosted"),)


def test_titles_can_be_turned_off() -> None:
    built = factory.build({**KEY, "DD_TITLE_MODEL": "none"})
    assert built.titler is None
    assert built.spec.models == (ModelUse("anthropic", DEFAULT_MODEL, "hosted"),)


def test_the_defaults() -> None:
    built = factory.build(KEY)
    assert DEFAULT_MODEL == "claude-sonnet-5-5"
    assert DEFAULT_TITLE_MODEL == "claude-haiku-5-5"
    assert built.titler is not None and built.titler.model_id == DEFAULT_TITLE_MODEL
    assert (built.history_turns, built.max_delegations) == (20, 4)


def test_it_runs_on_a_hosted_provider_other_than_anthropic() -> None:
    built = factory.build(OPENAI)
    assert built.model.provider == "openai" and built.model.model_id == "gpt-test"
    # The title is written by the same model unless another is named; no effort is sent.
    assert built.titler is not None and built.titler.model_id == "gpt-test"
    assert built.spec.models == (ModelUse("openai", "gpt-test", "hosted"),)
    assert getattr(built.model, "effort", None) is None
    titled = factory.build(
        {**OPENAI, "DD_TITLE_MODEL_ID": "gpt-mini", "DD_ORCHESTRATOR_EFFORT": "low"}
    )
    assert titled.spec.models == (
        ModelUse("openai", "gpt-test", "hosted"),
        ModelUse("openai", "gpt-mini", "hosted"),
    )
    assert getattr(titled.model, "effort", None) == "low"


def test_it_runs_on_a_local_endpoint_that_needs_no_key() -> None:
    built = factory.build({**LOCAL, "DD_TITLE_MODEL": "none"})
    assert built.spec.models == (ModelUse("localhost:11434", "llama-test", "local"),)


def test_it_runs_on_another_provider_through_the_broker() -> None:
    env = {
        "DD_MODEL_PROVIDER": "openai",
        "DD_MODEL_ID": "gpt-test",
        "DD_MODEL_BROKER_URL": "http://broker.test",
        "DD_MODEL_BROKER_CREDENTIAL": "c",
        "DD_TITLE_MODEL": "none",
    }
    built = factory.build(env)
    assert built.spec.models == (ModelUse("openai", "gpt-test", "hosted"),)


def test_claude_is_asked_for_effort_and_fallback() -> None:
    built = factory.build({**KEY, "DD_ORCHESTRATOR_EFFORT": "max"})
    assert getattr(built.model, "effort", None) == "max"
    assert getattr(built.model, "fallback", None) is True
    # The title model needs neither.
    assert getattr(built.titler, "fallback", None) is False


@pytest.mark.parametrize(
    "env",
    [
        {},
        {**KEY, "DD_ORCHESTRATOR_EFFORT": "extreme"},
        {**KEY, "DD_ORCHESTRATOR_HISTORY": "many"},
        {**KEY, "DD_ORCHESTRATOR_HISTORY": "-1"},
        {**KEY, "DD_ORCHESTRATOR_MAX_DELEGATIONS": "0"},
        {**KEY, "DD_TITLE_MODEL": "claude-haiku-5-5"},
        # An effort the provider does not name.
        {**OPENAI, "DD_ORCHESTRATOR_EFFORT": "max"},
        {**LOCAL, "DD_ORCHESTRATOR_EFFORT": "xhigh"},
        # Another provider has no default model.
        {"DD_MODEL_PROVIDER": "openai", "OPENAI_API_KEY": "k"},
        # An agent that calls through the broker holds no provider key.
        {**OPENAI, "DD_MODEL_BROKER_URL": "http://broker.test", "DD_MODEL_BROKER_CREDENTIAL": "c"},
    ],
)
def test_a_bad_setting_is_a_configuration_error(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        factory.build(env)

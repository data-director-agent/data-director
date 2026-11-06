"""The orchestrator's configuration: its model is declared, and a bad setting stops it at
start-up (docs/specs/policy-and-identity.md)."""

from __future__ import annotations

import pytest

from dd_agent_orchestrator_model import factory
from dd_agent_orchestrator_model.model import DEFAULT_MODEL
from dd_agent_orchestrator_model.title import DEFAULT_TITLE_MODEL
from dd_sdk.agent import ModelUse
from dd_sdk.credentials import ConfigError

KEY = {"ANTHROPIC_API_KEY": "sk-ant-test"}


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


@pytest.mark.parametrize(
    "env",
    [
        {},
        {**KEY, "DD_ORCHESTRATOR_EFFORT": "extreme"},
        {**KEY, "DD_ORCHESTRATOR_HISTORY": "many"},
        {**KEY, "DD_ORCHESTRATOR_HISTORY": "-1"},
        {**KEY, "DD_ORCHESTRATOR_MAX_DELEGATIONS": "0"},
        {**KEY, "DD_TITLE_MODEL": "claude-haiku-5-5"},
    ],
)
def test_a_bad_setting_is_a_configuration_error(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        factory.build(env)

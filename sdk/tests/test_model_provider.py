"""A model-backed agent's provider, model, key and hosting, from its settings
(docs/specs/policy-and-identity.md)."""

from __future__ import annotations

import pytest

from dd_sdk.credentials import ConfigError
from dd_sdk.model import declared
from dd_sdk.model_anthropic import AnthropicModel
from dd_sdk.model_openai import OpenAIModel
from dd_sdk.model_provider import configured_model, hosting_of, optional_model
from dd_sdk.model_route import RoutedModel

LOCAL = "http://localhost:11434/v1"


def test_anthropic_is_the_default_with_the_agents_own_model() -> None:
    model = configured_model({"ANTHROPIC_API_KEY": "k"}, default_model="claude-default")
    assert isinstance(model, AnthropicModel)
    assert declared(model).provider == "anthropic"
    assert declared(model).model == "claude-default"
    assert declared(model).hosting == "hosted"


@pytest.mark.parametrize(
    ("provider", "key"), [("openai", "OPENAI_API_KEY"), ("gemini", "GEMINI_API_KEY")]
)
def test_a_hosted_preset_declares_itself(provider: str, key: str) -> None:
    model = configured_model({"DD_MODEL_PROVIDER": provider, "DD_MODEL_ID": "m-1", key: "k"})
    assert isinstance(model, OpenAIModel)
    use = declared(model)
    assert (use.provider, use.model, use.hosting) == (provider, "m-1", "hosted")


def test_a_local_endpoint_needs_no_key_and_is_declared_local() -> None:
    env = {
        "DD_MODEL_PROVIDER": "openai-compatible",
        "DD_MODEL_ID": "llama",
        "DD_MODEL_BASE_URL": LOCAL,
    }
    use = declared(configured_model(env))
    assert (use.provider, use.model, use.hosting) == ("localhost:11434", "llama", "local")


def test_a_hosted_compatible_endpoint_is_declared_hosted() -> None:
    env = {
        "DD_MODEL_PROVIDER": "openai-compatible",
        "DD_MODEL_ID": "m",
        "DD_MODEL_BASE_URL": "https://llm.example.ac.uk/v1",
        "DD_MODEL_API_KEY": "k",
    }
    use = declared(configured_model(env))
    assert (use.provider, use.hosting) == ("llm.example.ac.uk", "hosted")


@pytest.mark.parametrize(
    ("url", "hosting"),
    [
        ("http://localhost:8000/v1", "local"),
        ("http://127.0.0.1:8000/v1", "local"),
        ("http://[::1]:8000/v1", "local"),
        ("http://10.1.2.3/v1", "local"),
        ("http://192.168.0.5:1234/v1", "local"),
        ("http://169.254.0.9/v1", "local"),
        ("http://[fd00::1]/v1", "local"),
        ("https://8.8.8.8/v1", "hosted"),
        ("https://api.openai.com/v1", "hosted"),
        ("https://llm.example.ac.uk/v1", "hosted"),
        # A name is not resolved, so a name for a loopback address is still hosted.
        ("http://localhost.example.com/v1", "hosted"),
    ],
)
def test_hosting_is_worked_out_from_the_endpoint(url: str, hosting: str) -> None:
    assert hosting_of(url) == hosting


@pytest.mark.parametrize(
    ("env", "names"),
    [
        ({"DD_MODEL_PROVIDER": "mistral"}, "DD_MODEL_PROVIDER"),
        ({"DD_MODEL_PROVIDER": "openai", "OPENAI_API_KEY": "k"}, "DD_MODEL_ID"),
        ({"DD_MODEL_PROVIDER": "openai", "DD_MODEL_ID": "m"}, "OPENAI_API_KEY"),
        (
            {
                "DD_MODEL_PROVIDER": "openai",
                "DD_MODEL_ID": "m",
                "OPENAI_API_KEY": "k",
                "OPENAI_API_KEY_FILE": "/k",
            },
            "OPENAI_API_KEY",
        ),
        ({"ANTHROPIC_API_KEY": "k", "OPENAI_API_KEY": "k"}, "OPENAI_API_KEY"),
        (
            {"DD_MODEL_PROVIDER": "openai", "DD_MODEL_ID": "m", "ANTHROPIC_API_KEY_FILE": "/k"},
            "ANTHROPIC_API_KEY",
        ),
        (
            {
                "DD_MODEL_PROVIDER": "openai",
                "DD_MODEL_ID": "m",
                "OPENAI_API_KEY": "k",
                "DD_MODEL_BASE_URL": LOCAL,
            },
            "DD_MODEL_BASE_URL",
        ),
        ({"DD_MODEL_PROVIDER": "openai-compatible", "DD_MODEL_ID": "m"}, "DD_MODEL_BASE_URL"),
        (
            {
                "DD_MODEL_PROVIDER": "openai-compatible",
                "DD_MODEL_ID": "m",
                "DD_MODEL_BASE_URL": "localhost:11434",
            },
            "DD_MODEL_BASE_URL",
        ),
        (
            {
                "DD_MODEL_PROVIDER": "openai-compatible",
                "DD_MODEL_ID": "m",
                "DD_MODEL_BASE_URL": "https://llm.example.ac.uk/v1",
            },
            "DD_MODEL_API_KEY",
        ),
        (
            {
                "DD_MODEL_PROVIDER": "openai",
                "DD_MODEL_ID": "m",
                "OPENAI_API_KEY": "k",
                "DD_MODEL_BROKER_URL": "http://127.0.0.1:7870",
                "DD_MODEL_BROKER_CREDENTIAL": "c",
            },
            "OPENAI_API_KEY",
        ),
        (
            {
                "DD_MODEL_PROVIDER": "openai-compatible",
                "DD_MODEL_ID": "m",
                "DD_MODEL_BASE_URL": LOCAL,
                "DD_MODEL_BROKER_URL": "http://127.0.0.1:7870",
                "DD_MODEL_BROKER_CREDENTIAL": "c",
            },
            "DD_MODEL_BASE_URL",
        ),
        (
            {
                "DD_MODEL_PROVIDER": "gemini",
                "DD_MODEL_ID": "m",
                "DD_MODEL_BROKER_URL": "http://127.0.0.1:7870",
            },
            "DD_MODEL_BROKER_CREDENTIAL",
        ),
    ],
)
def test_an_unusable_configuration_stops_start_up_in_one_line(
    env: dict[str, str], names: str
) -> None:
    with pytest.raises(ConfigError) as caught:
        configured_model(env, default_model="claude-default")
    message = str(caught.value)
    assert names in message
    assert "\n" not in message


def test_a_key_given_to_a_local_endpoint_is_still_read() -> None:
    env = {
        "DD_MODEL_PROVIDER": "openai-compatible",
        "DD_MODEL_ID": "m",
        "DD_MODEL_BASE_URL": LOCAL,
        "DD_MODEL_API_KEY_FILE": "relative",
    }
    # The file is read, so a broken one is an error and not a silent "no key".
    with pytest.raises(ConfigError, match="CREDENTIALS_DIRECTORY"):
        configured_model(env)


def test_anthropic_through_the_broker_holds_no_key() -> None:
    env = {
        "DD_MODEL_BROKER_URL": "http://127.0.0.1:7870",
        "DD_MODEL_BROKER_CREDENTIAL": "c",
    }
    model = configured_model(env, default_model="claude-default")
    # Routed through the broker (#843), as the model the card declares.
    assert isinstance(model, RoutedModel)
    assert isinstance(model.declared, AnthropicModel)
    assert (model.provider, model.model_id) == ("anthropic", "claude-default")


@pytest.mark.parametrize("name", ["openai", "gemini", "openai-compatible"])
def test_every_other_provider_through_the_broker_holds_no_key(name: str) -> None:
    env = {
        "DD_MODEL_PROVIDER": name,
        "DD_MODEL_ID": "m",
        "DD_MODEL_BROKER_URL": "http://127.0.0.1:7870/",
        "DD_MODEL_BROKER_CREDENTIAL": "c",
    }
    model = configured_model(env)
    assert isinstance(model, RoutedModel)
    assert isinstance(model.declared, OpenAIModel)
    # The card declares the provider the broker is asked for, and a hosted model: the endpoint a
    # person's account names is not known at start-up.
    assert (model.provider, model.hosting) == (name, "hosted")


@pytest.mark.parametrize(
    ("env", "effort"),
    [
        ({"ANTHROPIC_API_KEY": "k"}, "max"),
        ({"DD_MODEL_PROVIDER": "openai", "DD_MODEL_ID": "m", "OPENAI_API_KEY": "k"}, "high"),
        (
            {
                "DD_MODEL_PROVIDER": "openai-compatible",
                "DD_MODEL_ID": "m",
                "DD_MODEL_BASE_URL": LOCAL,
            },
            "low",
        ),
    ],
)
def test_an_effort_the_provider_names_is_sent(env: dict[str, str], effort: str) -> None:
    model = configured_model(env, default_model="claude-default", effort=effort)
    assert getattr(model, "effort", None) == effort


@pytest.mark.parametrize(
    ("env", "effort"),
    [
        ({"ANTHROPIC_API_KEY": "k"}, "extreme"),
        ({"DD_MODEL_PROVIDER": "gemini", "DD_MODEL_ID": "m", "GEMINI_API_KEY": "k"}, "max"),
        (
            {
                "DD_MODEL_PROVIDER": "openai-compatible",
                "DD_MODEL_ID": "m",
                "DD_MODEL_BASE_URL": LOCAL,
            },
            "xhigh",
        ),
    ],
)
def test_an_effort_the_provider_does_not_name_stops_start_up(
    env: dict[str, str], effort: str
) -> None:
    with pytest.raises(ConfigError, match="DD_TEST_EFFORT"):
        configured_model(
            env, default_model="claude-default", effort=effort, effort_setting="DD_TEST_EFFORT"
        )


def test_a_tool_loop_asks_claude_to_cache_and_fall_back() -> None:
    model = configured_model({"ANTHROPIC_API_KEY": "k"}, default_model="c", tool_use=True)
    assert isinstance(model, AnthropicModel)
    assert model.fallback and model.cache_system
    plain = configured_model({"ANTHROPIC_API_KEY": "k"}, default_model="c")
    assert isinstance(plain, AnthropicModel)
    assert not plain.fallback and not plain.cache_system


@pytest.mark.parametrize(
    "env",
    [
        {"ANTHROPIC_API_KEY": "k"},
        {"DD_MODEL_PROVIDER": "openai", "DD_MODEL_ID": "gpt-x", "OPENAI_API_KEY": "k"},
        {
            "DD_MODEL_PROVIDER": "openai-compatible",
            "DD_MODEL_ID": "llama-x",
            "DD_MODEL_BASE_URL": "http://localhost:11434/v1",
        },
    ],
)
def test_a_tool_loop_is_declared_on_the_card(env: dict[str, str]) -> None:
    assert declared(configured_model(env, default_model="c", tool_use=True)).tools
    assert not declared(configured_model(env, default_model="c")).tools


def test_an_optional_model_is_off_unless_the_agent_defaults_it_on() -> None:
    env = {"ANTHROPIC_API_KEY": "k"}
    assert optional_model(env, "DD_X") is None
    assert isinstance(
        optional_model(env, "DD_X", default_model="m", default="model"), AnthropicModel
    )
    assert optional_model({**env, "DD_X": "template"}, "DD_X", default="model") is None


def test_a_model_on_by_default_with_no_key_says_how_to_turn_it_off() -> None:
    with pytest.raises(ConfigError, match="DD_X=template"):
        optional_model({}, "DD_X", default_model="m", default="model")
    with pytest.raises(ConfigError) as raised:
        optional_model({"DD_X": "model"}, "DD_X", default_model="m", default="model")
    assert "DD_X=template" not in str(raised.value)

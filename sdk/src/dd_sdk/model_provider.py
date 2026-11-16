"""Which model a model-backed agent calls, and through whom, read once at start-up
(docs/specs/policy-and-identity.md).

`configured_model(env)` turns an agent's settings into a `dd_sdk.model.Model`:

- `DD_MODEL_PROVIDER`: `anthropic` (default), `openai`, `gemini` or `openai-compatible`.
- `DD_MODEL_ID`: the model. Only `anthropic` has a default, the agent's own; any other provider
  must name one.
- `DD_MODEL_BASE_URL`: the endpoint, for `openai-compatible` only (Ollama, vLLM, llama.cpp,
  LM Studio, a gateway). The other providers' endpoints are fixed.
- The provider's key, as `NAME` (development) or `NAME_FILE` (deployment), read by
  `dd_sdk.credentials.api_key`: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` or
  `DD_MODEL_API_KEY`. An agent holds one provider's key, so a key set for any other provider is an
  error rather than something left lying unused.

**No key.** Only an `openai-compatible` endpoint that is local may be called without a key: with
neither `DD_MODEL_API_KEY` nor `DD_MODEL_API_KEY_FILE` set, it is sent no `Authorization` header.
Every other provider, and a hosted `openai-compatible` endpoint, must have its key.

**Hosting** is worked out from where the calls go, never stated by the operator, because the
harness's rules on what an agent with a hosted model may be given read it (`hosting_of`).

**Effort.** An agent that sets one (the orchestrator's `DD_ORCHESTRATOR_EFFORT`) passes it to
`configured_model`, which refuses a value the provider does not name: `low`, `medium`, `high`,
`xhigh` or `max` for Claude; `low`, `medium` or `high` (`reasoning_effort`) for the others, which a
model that does not reason may ignore.

**The model broker** (`DD_MODEL_BROKER_URL`, docs/specs/model-accounts.md) serves every provider,
each below its own path in its own format, so the agent holds its broker credential in place of
the provider's key. The broker, not the agent, decides where an `openai-compatible` call goes, so
`DD_MODEL_BASE_URL` is refused beside it, and the model is declared `hosted`: which endpoint a
person's account names is not known at start-up, and calling a local model hosted only withholds
more from it.

Each problem is a `ConfigError` that names the variable, never a key, so the agent stops at
start-up in one line (`dd_sdk.serve.main`).
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from dd_sdk.credentials import BROKER_URL, ConfigError, ModelEndpoint, api_key, model_endpoint
from dd_sdk.model import Model, ModelCallError
from dd_sdk.model_anthropic import EFFORTS as CLAUDE_EFFORTS
from dd_sdk.model_anthropic import AnthropicModel
from dd_sdk.model_openai import EFFORTS as OPENAI_EFFORTS
from dd_sdk.model_openai import OpenAIModel
from dd_sdk.model_route import Builder, RoutedModel

PROVIDER = "DD_MODEL_PROVIDER"
MODEL_ID = "DD_MODEL_ID"
BASE_URL = "DD_MODEL_BASE_URL"
DEFAULT_PROVIDER = "anthropic"
COMPATIBLE = "openai-compatible"

type Hosting = Literal["hosted", "local"]


@dataclass(frozen=True)
class Provider:
    """One value of `DD_MODEL_PROVIDER`: the variable its key is read from, its endpoint (None:
    Anthropic's own, or `DD_MODEL_BASE_URL` for `openai-compatible`), the request field that
    caps a reply's length, and the efforts it accepts."""

    name: str
    key: str
    base_url: str | None = None
    max_tokens_field: str = "max_tokens"
    efforts: tuple[str, ...] = OPENAI_EFFORTS


PROVIDERS = {
    p.name: p
    for p in (
        Provider("anthropic", "ANTHROPIC_API_KEY", efforts=CLAUDE_EFFORTS),
        Provider("openai", "OPENAI_API_KEY", "https://api.openai.com/v1", "max_completion_tokens"),
        Provider(
            "gemini", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai/"
        ),
        Provider(COMPATIBLE, "DD_MODEL_API_KEY"),
    )
}


def hosting_of(base_url: str) -> Hosting:
    """`local` if `base_url`'s host is `localhost` or a loopback, private or link-local address
    written as an IP literal; otherwise `hosted`.

    A host name other than `localhost` is `hosted` even if it resolves to a private address: the
    name is not resolved, so the answer cannot change after start-up, and calling a local model
    hosted only withholds more from it."""
    host = (urlsplit(base_url).hostname or "").lower()
    if host == "localhost":
        return "local"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "hosted"
    local = address.is_loopback or address.is_private or address.is_link_local
    return "local" if local else "hosted"


def _endpoint_name(base_url: str) -> str:
    """Who serves an `openai-compatible` model, as the agent's card names it: the endpoint's host,
    and its port if the URL gives one."""
    parts = urlsplit(base_url)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    return f"{host}:{parts.port}" if parts.port else host


def _is_set(env: Mapping[str, str], name: str) -> bool:
    return bool((env.get(name) or "").strip() or env.get(f"{name}_FILE"))


def provider_name(env: Mapping[str, str]) -> str:
    """The provider `env` names, `anthropic` if none (not checked: `configured_model` checks)."""
    return (env.get(PROVIDER) or DEFAULT_PROVIDER).strip()


def configured_model(
    env: Mapping[str, str],
    *,
    default_model: str | None = None,
    effort: str | None = None,
    effort_setting: str = "effort",
    tool_use: bool = False,
) -> Model:
    """The model `env` configures. `default_model` is the agent's model when the provider is
    `anthropic` and `DD_MODEL_ID` is unset; no other provider has a default.

    `effort`, if given, is sent with every call; a value the provider does not accept is a
    `ConfigError` naming `effort_setting`, the agent's variable for it. `tool_use` is for an agent
    whose model runs a tool loop: its card then declares that it relies on tool calls
    (`ModelUse.tools`), and Claude caches the system prompt and may fall back to another model
    when it declines.

    Through the model broker, the model is routed: each run asks the broker which provider and
    model serve it (`dd_sdk.model_route`)."""
    declared = _declared_model(
        env,
        default_model=default_model,
        effort=effort,
        effort_setting=effort_setting,
        tool_use=tool_use,
    )
    broker_url = (env.get(BROKER_URL) or "").strip().rstrip("/")
    if not broker_url:
        return declared
    endpoint = model_endpoint(env, declared.provider, PROVIDERS[provider_name(env)].key)
    return RoutedModel(
        declared,
        broker_url=broker_url,
        credential=endpoint.api_key,
        build=_routed_builder(broker_url, endpoint.api_key, effort=effort, tool_use=tool_use),
    )


def _routed_builder(
    broker_url: str, credential: str, *, effort: str | None, tool_use: bool
) -> Builder:
    """Builds, for a provider and model the broker named, the adapter that calls it through the
    broker. The agent's effort goes with it only where that provider accepts it."""

    def build(name: str, model_id: str) -> Model:
        provider = PROVIDERS.get(name)
        if provider is None:
            raise ModelCallError(f"the model broker named a provider it does not serve: {name!r}")
        kept = effort if effort in provider.efforts else None
        endpoint = ModelEndpoint(credential, f"{broker_url}/{name}")
        if name == DEFAULT_PROVIDER:
            return AnthropicModel(
                model_id, endpoint=endpoint, effort=kept, cache_system=tool_use, tool_use=tool_use
            )
        assert endpoint.base_url is not None
        return OpenAIModel(
            model_id,
            provider=name,
            hosting="hosted",
            base_url=endpoint.base_url,
            api_key=endpoint.api_key,
            max_tokens_field=provider.max_tokens_field,
            effort=kept,
            brokered=True,
            tool_use=tool_use,
        )

    return build


def _declared_model(
    env: Mapping[str, str],
    *,
    default_model: str | None = None,
    effort: str | None = None,
    effort_setting: str = "effort",
    tool_use: bool = False,
) -> Model:
    """The adapter for the model `env` declares, as `configured_model` describes it."""
    name = provider_name(env)
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ConfigError(f"{PROVIDER}={name!r}: expected one of {', '.join(PROVIDERS)}")
    if effort is not None and effort not in provider.efforts:
        raise ConfigError(
            f"{effort_setting}={effort!r}: {PROVIDER}={name} accepts {', '.join(provider.efforts)}"
        )
    if foreign := [
        other.key
        for other in PROVIDERS.values()
        if other is not provider and _is_set(env, other.key)
    ]:
        raise ConfigError(
            f"{foreign[0]} is set but {PROVIDER} is {name}: an agent holds only its own provider's "
            f"key, {provider.key}"
        )
    model_id = (env.get(MODEL_ID) or "").strip() or (
        default_model if name == DEFAULT_PROVIDER else None
    )
    if not model_id:
        raise ConfigError(f"{MODEL_ID} is required with {PROVIDER}={name}")
    base_url = (env.get(BASE_URL) or "").strip()
    if name != COMPATIBLE and base_url:
        raise ConfigError(f"{BASE_URL} is for {PROVIDER}={COMPATIBLE} only; {name}'s is fixed")

    if name == DEFAULT_PROVIDER:
        return AnthropicModel(
            model_id,
            endpoint=model_endpoint(env),
            effort=effort,
            fallback=tool_use,
            cache_system=tool_use,
            tool_use=tool_use,
        )
    if (env.get(BROKER_URL) or "").strip():
        if base_url:
            raise ConfigError(
                f"set {BROKER_URL} or {BASE_URL}, not both: the model broker decides where an "
                f"{COMPATIBLE} call goes"
            )
        endpoint = model_endpoint(env, name, provider.key)
        return OpenAIModel(
            model_id,
            provider=name,
            hosting="hosted",
            base_url=endpoint.base_url,
            api_key=endpoint.api_key,
            max_tokens_field=provider.max_tokens_field,
            effort=effort,
            brokered=True,
            tool_use=tool_use,
        )

    if name == COMPATIBLE:
        if not base_url:
            raise ConfigError(f"{BASE_URL} is required with {PROVIDER}={COMPATIBLE}")
        if not base_url.startswith(("http://", "https://")):
            raise ConfigError(f"{BASE_URL} is not an http or https URL")
        hosting = hosting_of(base_url)
        # A local endpoint may need no key; leaving both variables unset says so.
        key = None
        if _is_set(env, provider.key):
            key = api_key(env, provider.key)
        elif hosting == "hosted":
            raise ConfigError(
                f"no model key: set {provider.key} or {provider.key}_FILE; only a local "
                f"{BASE_URL} may have none"
            )
        return OpenAIModel(
            model_id,
            provider=_endpoint_name(base_url),
            hosting=hosting,
            base_url=base_url,
            api_key=key,
            effort=effort,
            tool_use=tool_use,
        )
    assert provider.base_url is not None
    return OpenAIModel(
        model_id,
        provider=name,
        hosting="hosted",
        base_url=provider.base_url,
        api_key=api_key(env, provider.key),
        max_tokens_field=provider.max_tokens_field,
        effort=effort,
        tool_use=tool_use,
    )


def optional_model(
    env: Mapping[str, str],
    setting: str,
    *,
    default_model: str | None = None,
    default: Literal["template", "model"] = "template",
    tool_use: bool = False,
) -> Model | None:
    """For an agent that a model only helps: the model if `env[setting]` is `model`, None if it is
    `template`. Unset, it is `default`: `template` for most agents, `model` for one whose model is
    on unless an operator turns it off. `tool_use` is passed to `configured_model`, for an agent
    whose model runs a tool loop. `anthropic` is the older name for `model` with
    `DD_MODEL_PROVIDER` left as `anthropic`, so settings written before other providers keep
    working.

    A model that cannot be built is a `ConfigError`; when it was on only by default, the error
    says how to run without it."""
    choice = (env.get(setting) or "").strip() or default
    if choice == "template":
        return None
    if choice == "anthropic" and provider_name(env) != DEFAULT_PROVIDER:
        raise ConfigError(f"{setting}=anthropic but {PROVIDER} is not: set {setting}=model")
    if choice not in ("model", "anthropic"):
        raise ConfigError(f"{setting}={choice!r}: expected template or model")
    try:
        return configured_model(env, default_model=default_model, tool_use=tool_use)
    except ConfigError as error:
        if (env.get(setting) or "").strip():
            raise
        raise ConfigError(
            f"{error} ({setting} is model by default: set {setting}=template to run without a "
            "model)"
        ) from error

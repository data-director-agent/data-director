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

**The model broker** (`DD_MODEL_BROKER_URL`, docs/specs/model-accounts.md) forwards Anthropic's
format only, so it serves only `anthropic`.

Each problem is a `ConfigError` that names the variable, never a key, so the agent stops at
start-up in one line (`dd_sdk.serve.main`).
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from dd_sdk.credentials import BROKER_URL, ConfigError, api_key, model_endpoint
from dd_sdk.model import Model
from dd_sdk.model_anthropic import AnthropicModel
from dd_sdk.model_openai import OpenAIModel

PROVIDER = "DD_MODEL_PROVIDER"
MODEL_ID = "DD_MODEL_ID"
BASE_URL = "DD_MODEL_BASE_URL"
DEFAULT_PROVIDER = "anthropic"
COMPATIBLE = "openai-compatible"

type Hosting = Literal["hosted", "local"]


@dataclass(frozen=True)
class Provider:
    """One value of `DD_MODEL_PROVIDER`: the variable its key is read from, its endpoint (None:
    Anthropic's own, or `DD_MODEL_BASE_URL` for `openai-compatible`), and the request field that
    caps a reply's length."""

    name: str
    key: str
    base_url: str | None = None
    max_tokens_field: str = "max_tokens"


PROVIDERS = {
    p.name: p
    for p in (
        Provider("anthropic", "ANTHROPIC_API_KEY"),
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


def configured_model(env: Mapping[str, str], *, default_model: str | None = None) -> Model:
    """The model `env` configures. `default_model` is the agent's model when the provider is
    `anthropic` and `DD_MODEL_ID` is unset; no other provider has a default."""
    name = (env.get(PROVIDER) or DEFAULT_PROVIDER).strip()
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ConfigError(f"{PROVIDER}={name!r}: expected one of {', '.join(PROVIDERS)}")
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
        return AnthropicModel(model_id, endpoint=model_endpoint(env))
    if (env.get(BROKER_URL) or "").strip():
        # TODO(#832): forward the Chat Completions format through the broker.
        raise ConfigError(f"{BROKER_URL} is set but the model broker serves only anthropic")

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
        )
    assert provider.base_url is not None
    return OpenAIModel(
        model_id,
        provider=name,
        hosting="hosted",
        base_url=provider.base_url,
        api_key=api_key(env, provider.key),
        max_tokens_field=provider.max_tokens_field,
    )


def optional_model(
    env: Mapping[str, str], setting: str, *, default_model: str | None = None
) -> Model | None:
    """For an agent that a model only helps: the model if `env[setting]` is `model`, None if it is
    `template` or unset. `anthropic` is the older name for `model` with `DD_MODEL_PROVIDER` left
    as `anthropic`, so settings written before other providers keep working."""
    choice = (env.get(setting) or "template").strip()
    if choice == "template":
        return None
    if (
        choice == "anthropic"
        and (env.get(PROVIDER) or DEFAULT_PROVIDER).strip() != DEFAULT_PROVIDER
    ):
        raise ConfigError(f"{setting}=anthropic but {PROVIDER} is not: set {setting}=model")
    if choice not in ("model", "anthropic"):
        raise ConfigError(f"{setting}={choice!r}: expected template or model")
    return configured_model(env, default_model=default_model)

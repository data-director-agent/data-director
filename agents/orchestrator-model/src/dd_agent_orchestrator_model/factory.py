"""Factory and console script for orchestrator.model.

`build` assembles the orchestrator from its own environment variables
(`config/examples/agents/orchestrator-model.env`):

- `DD_MODEL_PROVIDER`, `DD_MODEL_ID`, `DD_MODEL_BASE_URL` and the provider's key: the model it
  calls, read by `dd_sdk.model_provider.configured_model` (docs/specs/policy-and-identity.md).
  There is no default key: this agent is a model. With Anthropic, the model is Claude Sonnet 5.5
  unless `DD_MODEL_ID` names another; any other provider must name one, and it must call tools
  (docs/specs/orchestration.md).
- `DD_ORCHESTRATOR_EFFORT`: Claude takes `low`, `medium`, `high` (default), `xhigh` or `max`;
  another provider takes `low`, `medium` or `high`, and is sent none if it is unset.
- `DD_ORCHESTRATOR_HISTORY`: how many earlier turns of the conversation it sends (default 20).
- `DD_ORCHESTRATOR_MAX_DELEGATIONS`: how many delegations one turn may make (default 4).
- `DD_TITLE_MODEL_ID`: the model that names a conversation on its first turn (`title.py`), from
  the same provider. Claude Haiku 5.5 by default with Anthropic, and the reply model otherwise.
- `DD_TITLE_MODEL`: `none` names no conversation, so no second model is sent the first message.

A missing key or a value out of range is a configuration error (`ConfigError`):
`dd-orchestrator-model serve` then stops at start-up. The spec declares the models it sends data to
(`AgentSpec.models`), from the models themselves (`dd_sdk.model.declared`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace

from dd_agent_orchestrator_model.agent import (
    DEFAULT_EFFORT,
    DEFAULT_HISTORY_TURNS,
    DEFAULT_MAX_DELEGATIONS,
    DEFAULT_MODEL,
    ModelOrchestrator,
)
from dd_agent_orchestrator_model.title import DEFAULT_TITLE_MODEL
from dd_sdk import serve
from dd_sdk.credentials import ConfigError
from dd_sdk.model import declared
from dd_sdk.model_provider import DEFAULT_PROVIDER, MODEL_ID, configured_model, provider_name

EFFORT = "DD_ORCHESTRATOR_EFFORT"


def _count(env: Mapping[str, str], name: str, default: int, minimum: int) -> int:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r}: expected a whole number") from None
    if value < minimum:
        raise ConfigError(f"{name}={raw!r}: expected at least {minimum}")
    return value


def build(env: Mapping[str, str] | None = None) -> ModelOrchestrator:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    claude = provider_name(env) == DEFAULT_PROVIDER
    effort = env.get(EFFORT) or (DEFAULT_EFFORT if claude else None)
    model = configured_model(
        env, default_model=DEFAULT_MODEL, effort=effort, effort_setting=EFFORT, tool_use=True
    )
    titles = env.get("DD_TITLE_MODEL")
    if titles not in (None, "none"):
        raise ConfigError(
            f"DD_TITLE_MODEL={titles!r}: expected none, or leave it unset and name the model "
            "with DD_TITLE_MODEL_ID"
        )
    titler = None
    if titles != "none":
        title_model_id = env.get("DD_TITLE_MODEL_ID") or (
            DEFAULT_TITLE_MODEL if claude else model.model_id
        )
        # The same provider and key; a title needs no effort, and no tools.
        titler = configured_model({**env, MODEL_ID: title_model_id})
    agent = ModelOrchestrator(
        model,
        history_turns=_count(env, "DD_ORCHESTRATOR_HISTORY", DEFAULT_HISTORY_TURNS, 0),
        max_delegations=_count(env, "DD_ORCHESTRATOR_MAX_DELEGATIONS", DEFAULT_MAX_DELEGATIONS, 1),
        titler=titler,
    )
    models = [declared(model)]
    if titler is not None and declared(titler) not in models:
        models.append(declared(titler))
    agent.spec = replace(agent.spec, models=tuple(models))
    return agent


def main() -> int:
    """Console script: serve the orchestrator over A2A (`dd_sdk.serve`)."""
    return serve.main(build)

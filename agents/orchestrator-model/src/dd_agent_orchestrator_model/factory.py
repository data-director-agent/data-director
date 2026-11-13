"""Factory and console script for orchestrator.model.

`build` assembles the orchestrator from its own environment variables
(`config/examples/agents/orchestrator-model.env`):

- `ANTHROPIC_API_KEY` (development) or `ANTHROPIC_API_KEY_FILE` (deployment): the key, read at
  start-up (`dd_sdk.credentials`, docs/specs/policy-and-identity.md). There is no default: this
  agent is a model.
- `DD_MODEL_ID`: the model it calls. Claude Sonnet 5.5 by default;
  a deployment may name a smaller or a more capable one.
- `DD_ORCHESTRATOR_EFFORT`: `low`, `medium`, `high` (default), `xhigh` or `max`.
- `DD_ORCHESTRATOR_HISTORY`: how many earlier turns of the conversation it sends (default 20).
- `DD_ORCHESTRATOR_MAX_DELEGATIONS`: how many delegations one turn may make (default 4).
- `DD_TITLE_MODEL_ID`: the model that names a conversation on its first turn (`title.py`).
  Claude Haiku 5.5 by default.
- `DD_TITLE_MODEL`: `none` names no conversation, so no second model is sent the first message.

A missing key or a value out of range is a configuration error (`ConfigError`):
`dd-orchestrator-model serve` then stops at start-up. The spec declares the models it sends data to
(`AgentSpec.models`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace

from dd_agent_orchestrator_model.agent import (
    DEFAULT_HISTORY_TURNS,
    DEFAULT_MAX_DELEGATIONS,
    ModelOrchestrator,
)
from dd_agent_orchestrator_model.model import DEFAULT_EFFORT, DEFAULT_MODEL, EFFORTS, AnthropicModel
from dd_agent_orchestrator_model.title import DEFAULT_TITLE_MODEL, AnthropicTitler
from dd_sdk import serve
from dd_sdk.agent import ModelUse
from dd_sdk.credentials import ConfigError, model_endpoint


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
    effort = env.get("DD_ORCHESTRATOR_EFFORT", DEFAULT_EFFORT)
    if effort not in EFFORTS:
        raise ConfigError(
            f"DD_ORCHESTRATOR_EFFORT={effort!r}: expected one of {', '.join(EFFORTS)}"
        )
    model_id = env.get("DD_MODEL_ID", DEFAULT_MODEL)
    titles = env.get("DD_TITLE_MODEL")
    if titles not in (None, "none"):
        raise ConfigError(
            f"DD_TITLE_MODEL={titles!r}: expected none, or leave it unset and name the model "
            "with DD_TITLE_MODEL_ID"
        )
    title_model_id = None if titles == "none" else env.get("DD_TITLE_MODEL_ID", DEFAULT_TITLE_MODEL)
    endpoint = model_endpoint(env)
    agent = ModelOrchestrator(
        AnthropicModel(model_id=model_id, effort=effort, endpoint=endpoint),
        history_turns=_count(env, "DD_ORCHESTRATOR_HISTORY", DEFAULT_HISTORY_TURNS, 0),
        max_delegations=_count(env, "DD_ORCHESTRATOR_MAX_DELEGATIONS", DEFAULT_MAX_DELEGATIONS, 1),
        titler=(
            AnthropicTitler(model_id=title_model_id, endpoint=endpoint) if title_model_id else None
        ),
    )
    models = [ModelUse("anthropic", model_id, "hosted")]
    if title_model_id and title_model_id != model_id:
        models.append(ModelUse("anthropic", title_model_id, "hosted"))
    agent.spec = replace(agent.spec, models=tuple(models))
    return agent


def main() -> int:
    """Console script: serve the orchestrator over A2A (`dd_sdk.serve`)."""
    return serve.main(build)

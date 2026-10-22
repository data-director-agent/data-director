"""Factory and console script for orchestrator.model.

`build` assembles the orchestrator from its own environment variables
(`workbench/agents/env.example`):

- `ANTHROPIC_API_KEY` (development) or `ANTHROPIC_API_KEY_FILE` (deployment): the key, read at
  start-up (`dd_sdk.credentials`, ADR-0026). There is no default: this agent is a model.
- `DD_MODEL_ID`: the model it calls. Claude Fable 5.1 by default, the most capable model
  available, since the orchestrator weighs each request before handing it on.
- `DD_ORCHESTRATOR_EFFORT`: `low`, `medium`, `high` (default), `xhigh` or `max`.
- `DD_ORCHESTRATOR_HISTORY`: how many earlier turns of the conversation it sends (default 20).
- `DD_ORCHESTRATOR_MAX_DELEGATIONS`: how many delegations one turn may make (default 4).

A missing key or a value out of range is a configuration error (`ConfigError`):
`dd-orchestrator serve` then stops at start-up. The spec declares the model it sends data to
(`AgentSpec.models`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace

from dd_agent_orchestrator.agent import (
    DEFAULT_HISTORY_TURNS,
    DEFAULT_MAX_DELEGATIONS,
    ModelOrchestrator,
)
from dd_agent_orchestrator.model import DEFAULT_EFFORT, DEFAULT_MODEL, EFFORTS, AnthropicModel
from dd_sdk import serve
from dd_sdk.agent import ModelUse
from dd_sdk.credentials import ConfigError, api_key


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
    agent = ModelOrchestrator(
        AnthropicModel(model_id=model_id, effort=effort, api_key=api_key(env)),
        history_turns=_count(env, "DD_ORCHESTRATOR_HISTORY", DEFAULT_HISTORY_TURNS, 0),
        max_delegations=_count(env, "DD_ORCHESTRATOR_MAX_DELEGATIONS", DEFAULT_MAX_DELEGATIONS, 1),
    )
    agent.spec = replace(agent.spec, models=(ModelUse("anthropic", model_id, "hosted"),))
    return agent


def main() -> int:
    """Console script: serve the orchestrator over A2A (`dd_sdk.serve`)."""
    return serve.main(build)

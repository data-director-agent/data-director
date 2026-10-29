"""Factory and console script for the repository advisor.

`build` assembles the agent from its own environment variables (documented in
`config/examples/agents.env`):

- `DD_REPOSITORY_RETRIEVAL`: `snapshot` (default) reads the committed copies of re3data and
  FAIRsharing. `live` asks both registries' public routes, which need no account, and falls back
  to the snapshots, marked stale, when a route fails.
- `DD_REPOSITORY_EXPLAINER`: `template` (default) or `anthropic`.
- `DD_MODEL_ID`: the model the Anthropic explainer calls.
- `ANTHROPIC_API_KEY` (development) or `ANTHROPIC_API_KEY_FILE` (deployment): the Anthropic
  explainer's key, read at start-up (`dd_sdk.credentials`, ADR-0026).

An unknown value, or the Anthropic explainer with no key, is a configuration error
(`ConfigError`), and `dd-advisor-repository serve` stops at start-up. With the Anthropic
explainer the spec declares the model it sends data to (`AgentSpec.models`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace

from dd_agent_advisor_repository.agent import RepositoryAgent
from dd_agent_advisor_repository.explain import (
    DEFAULT_MODEL,
    AnthropicExplainer,
    Explainer,
    TemplateExplainer,
)
from dd_agent_advisor_repository.live import FairsharingLive, Re3dataLive
from dd_agent_advisor_repository.snapshot import FairsharingSnapshot, Re3dataSnapshot
from dd_sdk import serve
from dd_sdk.agent import ModelUse
from dd_sdk.credentials import ConfigError, api_key


def build_explainer(env: Mapping[str, str]) -> Explainer:
    choice = env.get("DD_REPOSITORY_EXPLAINER", "template")
    if choice == "template":
        return TemplateExplainer()
    if choice == "anthropic":
        return AnthropicExplainer(
            model_id=env.get("DD_MODEL_ID", DEFAULT_MODEL), api_key=api_key(env)
        )
    raise ConfigError(f"DD_REPOSITORY_EXPLAINER={choice!r}: expected template or anthropic")


def build(env: Mapping[str, str] | None = None) -> RepositoryAgent:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    explainer = build_explainer(env)
    choice = env.get("DD_REPOSITORY_RETRIEVAL", "snapshot")
    if choice == "snapshot":
        agent = RepositoryAgent(Re3dataSnapshot(), FairsharingSnapshot(), explainer)
    elif choice == "live":
        agent = RepositoryAgent(
            Re3dataLive(),
            FairsharingLive(),
            explainer,
            fallback=Re3dataSnapshot(),
            databases_fallback=FairsharingSnapshot(),
        )
    else:
        raise ConfigError(f"DD_REPOSITORY_RETRIEVAL={choice!r}: expected snapshot or live")
    if isinstance(explainer, AnthropicExplainer) and explainer.model_id:
        agent.spec = replace(
            agent.spec, models=(ModelUse("anthropic", explainer.model_id, "hosted"),)
        )
    return agent


def main() -> int:
    """Console script: serve the repository advisor over A2A (`dd_sdk.serve`)."""
    return serve.main(build)

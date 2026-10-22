"""Factory and console script for R3.

`build` assembles the standards advisor from its own environment variables (documented in
`workbench/env.example`):

- `DD_STANDARDS_RETRIEVAL`: `snapshot` (default) searches the committed FAIRsharing snapshot. `live`
  searches FAIRsharing (`FAIRSHARING_LOGIN` / `FAIRSHARING_PASSWORD`) and, when the live route
  fails, falls back to the snapshot and marks it stale.
- `DD_STANDARDS_EXPLAINER`: `template` (default) or `anthropic`.
- `DD_MODEL_ID`: the model the Anthropic explainer calls.
- `ANTHROPIC_API_KEY` (development) or `ANTHROPIC_API_KEY_FILE` (deployment): the Anthropic
  explainer's key, read at start-up (`dd_sdk.credentials`, ADR-0026).
- `DD_SNAPSHOT_PATH`: the snapshot file. The default is the committed one.

An unknown value, or the Anthropic explainer with no key, is a configuration error
(`ConfigError`). `dd-standards serve` then stops at start-up instead of serving something other
than what was configured. With the Anthropic explainer the spec declares the model it sends data
to (`AgentSpec.models`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from dd_agent_standards.agent import StandardsAgent
from dd_agent_standards.explain import (
    DEFAULT_MODEL,
    AnthropicExplainer,
    Explainer,
    TemplateExplainer,
)
from dd_agent_standards.fairsharing.live import LiveBackend
from dd_agent_standards.fairsharing.snapshot import DEFAULT_SNAPSHOT, SnapshotBackend
from dd_sdk import serve
from dd_sdk.agent import ModelUse
from dd_sdk.credentials import ConfigError, api_key


def build_explainer(env: Mapping[str, str]) -> Explainer:
    choice = env.get("DD_STANDARDS_EXPLAINER", "template")
    if choice == "template":
        return TemplateExplainer()
    if choice == "anthropic":
        return AnthropicExplainer(
            model_id=env.get("DD_MODEL_ID", DEFAULT_MODEL), api_key=api_key(env)
        )
    raise ConfigError(f"DD_STANDARDS_EXPLAINER={choice!r}: expected template or anthropic")


def build(env: Mapping[str, str] | None = None) -> StandardsAgent:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    snapshot = SnapshotBackend(Path(env.get("DD_SNAPSHOT_PATH", str(DEFAULT_SNAPSHOT))))
    choice = env.get("DD_STANDARDS_RETRIEVAL", "snapshot")
    if choice == "snapshot":
        agent = StandardsAgent(retrieval=snapshot, explainer=build_explainer(env))
    elif choice == "live":
        live = LiveBackend(
            login=env.get("FAIRSHARING_LOGIN"), password=env.get("FAIRSHARING_PASSWORD")
        )
        agent = StandardsAgent(retrieval=live, fallback=snapshot, explainer=build_explainer(env))
    else:
        raise ConfigError(f"DD_STANDARDS_RETRIEVAL={choice!r}: expected snapshot or live")
    if isinstance(agent.explainer, AnthropicExplainer) and agent.explainer.model_id:
        agent.spec = replace(
            agent.spec, models=(ModelUse("anthropic", agent.explainer.model_id, "hosted"),)
        )
    return agent


def main() -> int:
    """Console script: serve the standards advisor over A2A (`dd_sdk.serve`)."""
    return serve.main(build)

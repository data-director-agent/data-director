"""Factory and console script for R3.

`build` assembles the standards advisor from its own environment variables (documented in
`config/examples/agents.env`):

- `DD_STANDARDS_RETRIEVAL`: `snapshot` (default) searches the committed FAIRsharing snapshot. `live`
  searches FAIRsharing (`FAIRSHARING_LOGIN` / `FAIRSHARING_PASSWORD`) and, when the live route
  fails, falls back to the snapshot and marks it stale.
- `DD_STANDARDS_EXPLAINER`: `model` (default) has a model write the rationales, note concerns
  and add recommendations from records it may search for (`advise.ModelAdvisor`); `template`
  calls no model (`anthropic`, the older name for `model`, still works).
- `DD_STANDARDS_MAX_LOOKUPS`: the most searches the model may make in one run (4 by default; 0
  offers it none).
- With `model`: `DD_MODEL_PROVIDER` (`anthropic` by default), `DD_MODEL_ID` (Claude Sonnet 5.5
  by default for Anthropic), `DD_MODEL_BASE_URL` and the provider's key, read at start-up
  (`dd_sdk.model_provider`, docs/specs/policy-and-identity.md).
- `DD_SNAPSHOT_PATH`: the snapshot file. The default is the committed one.

An unknown value, or an unusable model setting, is a configuration error
(`ConfigError`). `dd-advisor-standards serve` then stops at start-up instead of serving
something other than what was configured. With the model explainer the spec declares the
model it sends data to (`AgentSpec.models`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from dd_agent_advisor_standards.advise import DEFAULT_MAX_LOOKUPS, DEFAULT_MODEL, ModelAdvisor
from dd_agent_advisor_standards.agent import StandardsAgent
from dd_agent_advisor_standards.explain import Explainer, TemplateExplainer
from dd_agent_advisor_standards.fairsharing.live import LiveBackend
from dd_agent_advisor_standards.fairsharing.snapshot import DEFAULT_SNAPSHOT, SnapshotBackend
from dd_sdk import serve
from dd_sdk.credentials import ConfigError
from dd_sdk.model import declared
from dd_sdk.model_provider import optional_model

__all__ = ["DEFAULT_MAX_LOOKUPS", "build", "build_explainer", "main", "max_lookups"]

SWITCH = "DD_STANDARDS_EXPLAINER"
MAX_LOOKUPS = 30


def max_lookups(env: Mapping[str, str]) -> int:
    raw = (env.get("DD_STANDARDS_MAX_LOOKUPS") or "").strip()
    if not raw:
        return DEFAULT_MAX_LOOKUPS
    try:
        value = int(raw)
    except ValueError:
        value = -1
    if not 0 <= value <= MAX_LOOKUPS:
        raise ConfigError(
            f"DD_STANDARDS_MAX_LOOKUPS={raw!r}: expected a whole number from 0 to {MAX_LOOKUPS}"
        )
    return value


def build_explainer(env: Mapping[str, str]) -> Explainer:
    model = optional_model(env, SWITCH, default_model=DEFAULT_MODEL, default="model", tool_use=True)
    return TemplateExplainer() if model is None else ModelAdvisor(model, max_lookups(env))


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
    if isinstance(agent.explainer, ModelAdvisor):
        agent.spec = replace(agent.spec, models=(declared(agent.explainer.model),))
    return agent


def main() -> int:
    """Console script: serve the standards advisor over A2A (`dd_sdk.serve`)."""
    return serve.main(build)

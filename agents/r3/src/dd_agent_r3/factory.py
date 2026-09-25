"""Factory and console script for R3.

`build` assembles R3 from its own environment variables (documented in `workbench/env.example`):

- `DD_R3_RETRIEVAL`: `snapshot` (default) searches the committed FAIRsharing snapshot. `live`
  searches FAIRsharing (`FAIRSHARING_LOGIN` / `FAIRSHARING_PASSWORD`) and, when the live route
  fails, falls back to the snapshot and marks it stale.
- `DD_R3_EXPLAINER`: `template` (default) or `anthropic`.
- `DD_MODEL_ID`: the model the Anthropic explainer calls.
- `DD_SNAPSHOT_PATH`: the snapshot file. The default is the committed one.

An unknown value is a configuration error. `dd-r3 serve` then stops at start-up instead of
serving something other than what was configured.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from dd_agent_r3.agent import R3Agent
from dd_agent_r3.explain import DEFAULT_MODEL, AnthropicExplainer, Explainer, TemplateExplainer
from dd_agent_r3.fairsharing.live import LiveBackend
from dd_agent_r3.fairsharing.snapshot import DEFAULT_SNAPSHOT, SnapshotBackend
from dd_sdk import serve


def build_explainer(env: Mapping[str, str]) -> Explainer:
    choice = env.get("DD_R3_EXPLAINER", "template")
    if choice == "template":
        return TemplateExplainer()
    if choice == "anthropic":
        return AnthropicExplainer(model_id=env.get("DD_MODEL_ID", DEFAULT_MODEL))
    raise ValueError(f"DD_R3_EXPLAINER={choice!r}: expected template or anthropic")


def build(env: Mapping[str, str] | None = None) -> R3Agent:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    snapshot = SnapshotBackend(Path(env.get("DD_SNAPSHOT_PATH", str(DEFAULT_SNAPSHOT))))
    choice = env.get("DD_R3_RETRIEVAL", "snapshot")
    if choice == "snapshot":
        return R3Agent(retrieval=snapshot, explainer=build_explainer(env))
    if choice == "live":
        live = LiveBackend(
            login=env.get("FAIRSHARING_LOGIN"), password=env.get("FAIRSHARING_PASSWORD")
        )
        return R3Agent(retrieval=live, fallback=snapshot, explainer=build_explainer(env))
    raise ValueError(f"DD_R3_RETRIEVAL={choice!r}: expected snapshot or live")


def main() -> int:
    """Console script: serve R3 over A2A (`dd_sdk.serve`)."""
    return serve.main(build)

"""Factory and console script for the repository advisor.

`build` assembles the agent from its own environment variables (documented in
`config/examples/agents.env`):

- `DD_REPOSITORY_RETRIEVAL`: how FAIRsharing's database records are read. `snapshot` (default)
  reads the committed copy; `live` asks FAIRsharing's public route, which needs no account, and
  falls back to the snapshot, marked stale, when it fails. re3data is always read from the
  registry built from its pinned export (`registry.py`, `dd-sources prepare`), and the
  repositories it does not list from DataCite's committed snapshot (`datacite.py`).
- `DD_REPOSITORY_EXPLAINER`: `model` (default), which has a model write the rationale
  (`anthropic`, its older name, still works), or `template`, which writes it from a template and
  needs no key.
- The model's provider, id and key: as for every advisor (docs/guide/operations/ai-models.md).

An unknown value, or an unusable model setting, is a configuration error
(`ConfigError`), and `dd-advisor-repository serve` stops at start-up: with the setting unset and
no model key, the error says to set `DD_REPOSITORY_EXPLAINER=template` to run without a model.
With the model explainer the spec declares the model it sends data to (`AgentSpec.models`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace

from dd_agent_advisor_repository.agent import RepositoryAgent
from dd_agent_advisor_repository.datacite import DataciteRegistry, Registries
from dd_agent_advisor_repository.explain import (
    DEFAULT_MODEL,
    Explainer,
    ModelExplainer,
    TemplateExplainer,
)
from dd_agent_advisor_repository.live import FairsharingLive
from dd_agent_advisor_repository.snapshot import FairsharingSnapshot, Re3dataRegistry
from dd_sdk import serve
from dd_sdk.credentials import ConfigError
from dd_sdk.model import declared
from dd_sdk.model_provider import optional_model

SWITCH = "DD_REPOSITORY_EXPLAINER"


def build_explainer(env: Mapping[str, str]) -> Explainer:
    model = optional_model(env, SWITCH, default_model=DEFAULT_MODEL)
    return TemplateExplainer() if model is None else ModelExplainer(model)


def build(env: Mapping[str, str] | None = None) -> RepositoryAgent:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    explainer = build_explainer(env)
    choice = env.get("DD_REPOSITORY_RETRIEVAL", "snapshot")
    repositories = Registries(Re3dataRegistry(), DataciteRegistry())
    if choice == "snapshot":
        agent = RepositoryAgent(repositories, FairsharingSnapshot(), explainer)
    elif choice == "live":
        agent = RepositoryAgent(
            repositories,
            FairsharingLive(),
            explainer,
            databases_fallback=FairsharingSnapshot(),
        )
    else:
        raise ConfigError(f"DD_REPOSITORY_RETRIEVAL={choice!r}: expected snapshot or live")
    if isinstance(explainer, ModelExplainer):
        agent.spec = replace(agent.spec, models=(declared(explainer.model),))
    return agent


def main() -> int:
    """Console script: serve the repository advisor over A2A (`dd_sdk.serve`)."""
    return serve.main(build)

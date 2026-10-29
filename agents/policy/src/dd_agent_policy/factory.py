"""Factory and console script for the policy advisor.

`build` assembles the agent from its own environment variables (documented in
`config/examples/agents.env`):

- `DD_POLICY_RETRIEVAL`: `snapshot` (default) reads the committed copy of FAIRsharing's policy
  records. `live` searches FAIRsharing, which needs an account (`FAIRSHARING_LOGIN`, and
  `FAIRSHARING_PASSWORD` or `FAIRSHARING_PASSWORD_FILE`), and falls back to the snapshot,
  marked stale, when the route fails.
- `DD_POLICY_EXPLAINER`: `template` (default) or `anthropic`.
- `DD_MODEL_ID`: the model the Anthropic explainer calls.
- `ANTHROPIC_API_KEY` (development) or `ANTHROPIC_API_KEY_FILE` (deployment): the Anthropic
  explainer's key, read at start-up (`dd_sdk.credentials`, ADR-0026).

An unknown value, live retrieval with no account, or the Anthropic explainer with no key is a
configuration error (`ConfigError`), and `dd-policy serve` stops at start-up. With the Anthropic
explainer the spec declares the model it sends data to (`AgentSpec.models`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace

from dd_agent_policy.agent import PolicyAgent
from dd_agent_policy.explain import (
    DEFAULT_MODEL,
    AnthropicExplainer,
    Explainer,
    TemplateExplainer,
)
from dd_agent_policy.live import PolicyLive
from dd_agent_policy.snapshot import PolicySnapshot
from dd_sdk import serve
from dd_sdk.agent import ModelUse
from dd_sdk.credentials import ConfigError, api_key


def build_explainer(env: Mapping[str, str]) -> Explainer:
    choice = env.get("DD_POLICY_EXPLAINER", "template")
    if choice == "template":
        return TemplateExplainer()
    if choice == "anthropic":
        return AnthropicExplainer(
            model_id=env.get("DD_MODEL_ID", DEFAULT_MODEL), api_key=api_key(env)
        )
    raise ConfigError(f"DD_POLICY_EXPLAINER={choice!r}: expected template or anthropic")


def build(env: Mapping[str, str] | None = None) -> PolicyAgent:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    explainer = build_explainer(env)
    choice = env.get("DD_POLICY_RETRIEVAL", "snapshot")
    if choice == "snapshot":
        agent = PolicyAgent(PolicySnapshot(), explainer)
    elif choice == "live":
        login = env.get("FAIRSHARING_LOGIN")
        if not (
            login and (env.get("FAIRSHARING_PASSWORD") or env.get("FAIRSHARING_PASSWORD_FILE"))
        ):
            raise ConfigError(
                "DD_POLICY_RETRIEVAL=live: FAIRsharing search needs FAIRSHARING_LOGIN and "
                "FAIRSHARING_PASSWORD (or FAIRSHARING_PASSWORD_FILE)"
            )
        # Read as a credential, so the password may be a file under $CREDENTIALS_DIRECTORY.
        password = api_key(env, "FAIRSHARING_PASSWORD")
        agent = PolicyAgent(
            PolicyLive(login=login, password=password), explainer, fallback=PolicySnapshot()
        )
    else:
        raise ConfigError(f"DD_POLICY_RETRIEVAL={choice!r}: expected snapshot or live")
    if isinstance(explainer, AnthropicExplainer) and explainer.model_id:
        agent.spec = replace(
            agent.spec, models=(ModelUse("anthropic", explainer.model_id, "hosted"),)
        )
    return agent


def main() -> int:
    """Console script: serve the policy advisor over A2A (`dd_sdk.serve`)."""
    return serve.main(build)

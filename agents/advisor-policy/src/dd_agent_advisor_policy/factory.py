"""Factory and console script for the policy advisor.

`build` assembles the agent from its own environment variables (documented in
`config/examples/agents.env`):

- `DD_POLICY_RETRIEVAL`: `snapshot` (default) reads the committed copy of FAIRsharing's policy
  records. `live` searches FAIRsharing, which needs an account (`FAIRSHARING_LOGIN`, and
  `FAIRSHARING_PASSWORD` or `FAIRSHARING_PASSWORD_FILE`), and falls back to the snapshot,
  marked stale, when the route fails.
- `DD_POLICY_ROR`: `snapshot` (default) identifies funders in the ROR registry built from its
  pinned dump (`uv run dd-sources prepare` builds it); `live` asks ROR's API, which needs no
  account, and falls back to the built registry, marked stale, when the route fails. Where
  neither answers, funders are searched by the name given and the statement says so.
- `DD_POLICY_EXPLAINER`: `template` (default) or `model`, which has a model write the rationale
  (`anthropic`, its older name, still works).
- With `model`: `DD_MODEL_PROVIDER` (`anthropic` by default), `DD_MODEL_ID` (Claude Sonnet 5.5
  by default for Anthropic), `DD_MODEL_BASE_URL` and the provider's key, read at start-up
  (`dd_sdk.model_provider`, docs/specs/policy-and-identity.md).

An unknown value, live retrieval with no account, or an unusable model setting is a
configuration error (`ConfigError`), and `dd-advisor-policy serve` stops at start-up. With
the model explainer the spec declares the model it sends data to (`AgentSpec.models`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace

from dd_agent_advisor_policy.agent import PolicyAgent
from dd_agent_advisor_policy.explain import (
    DEFAULT_MODEL,
    Explainer,
    ModelExplainer,
    TemplateExplainer,
)
from dd_agent_advisor_policy.live import PolicyLive
from dd_agent_advisor_policy.ror import RorDump, RorLive
from dd_agent_advisor_policy.snapshot import PolicySnapshot
from dd_sdk import serve
from dd_sdk.credentials import ConfigError, api_key
from dd_sdk.model import declared
from dd_sdk.model_provider import optional_model


def build_explainer(env: Mapping[str, str]) -> Explainer:
    model = optional_model(env, "DD_POLICY_EXPLAINER", default_model=DEFAULT_MODEL)
    return TemplateExplainer() if model is None else ModelExplainer(model)


def build(env: Mapping[str, str] | None = None) -> PolicyAgent:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    explainer = build_explainer(env)
    ror_choice = env.get("DD_POLICY_ROR", "snapshot")
    if ror_choice not in ("snapshot", "live"):
        raise ConfigError(f"DD_POLICY_ROR={ror_choice!r}: expected snapshot or live")
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
    if ror_choice == "live":
        agent.organisations, agent.organisations_fallback = RorLive(), RorDump()
    else:
        agent.organisations = RorDump()
    if isinstance(explainer, ModelExplainer):
        agent.spec = replace(agent.spec, models=(declared(explainer.model),))
    return agent


def main() -> int:
    """Console script: serve the policy advisor over A2A (`dd_sdk.serve`)."""
    return serve.main(build)

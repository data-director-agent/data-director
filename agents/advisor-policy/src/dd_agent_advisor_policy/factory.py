"""Factory and console script for the policy advisor.

`build` assembles the agent from its own environment variables (documented in
`config/examples/agents.env`):

- `DD_POLICY_ADVISOR`: `model` (default) has a model read the policy records found, search for
  more with read-only tools, and state each policy's obligations with quotes the agent checks
  (`advise.py`); `template` writes the rationale from a template, reads obligations from curated
  fields only, and needs no key. `DD_POLICY_EXPLAINER`, its older name, still works.
- `DD_POLICY_MAX_LOOKUPS`: the most searches the model may make in one run (6 by default; 0
  leaves it only the records the first search found).
- `OPEN_POLICY_FINDER_API_KEY` or `OPEN_POLICY_FINDER_API_KEY_FILE`: a free Jisc Open Policy
  Finder key. Without one, Open Policy Finder is not searched and each run's statement says so.
- `DD_POLICY_CROSSREF`: `live` (default) asks Crossref which publisher a journal belongs to;
  `off` does not.
- `DD_POLICY_RETRIEVAL`: `snapshot` (default) reads the committed copy of FAIRsharing's policy
  records. `live` searches FAIRsharing, which needs an account (`FAIRSHARING_LOGIN`, and
  `FAIRSHARING_PASSWORD` or `FAIRSHARING_PASSWORD_FILE`), and falls back to the snapshot,
  marked stale, when the route fails.
- `DD_POLICY_ROR`: `snapshot` (default) identifies funders in the ROR registry built from its
  pinned dump (`uv run dd-sources prepare` builds it); `live` asks ROR's API, which needs no
  account, and falls back to the built registry, marked stale, when the route fails. Where
  neither answers, funders are searched by the name given and the statement says so.
- With `model`: `DD_MODEL_PROVIDER` (`anthropic` by default), `DD_MODEL_ID` (Claude Sonnet 5.5
  by default for Anthropic), `DD_MODEL_BASE_URL` and the provider's key, read at start-up
  (`dd_sdk.model_provider`, docs/specs/policy-and-identity.md).

An unknown value, live retrieval with no account, or an unusable model setting is a
configuration error (`ConfigError`), and `dd-advisor-policy serve` stops at start-up: with the
setting unset and no model key, the error says to set `DD_POLICY_ADVISOR=template` to run without
a model. With the model advisor the spec declares the model it sends registry text to, and that
it relies on tool calls (`AgentSpec.models`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace

from dd_agent_advisor_policy.advise import DEFAULT_MAX_LOOKUPS, DEFAULT_MODEL, ModelAdvisor
from dd_agent_advisor_policy.agent import PolicyAgent
from dd_agent_advisor_policy.crossref import CrossrefJournals
from dd_agent_advisor_policy.explain import Explainer, TemplateExplainer
from dd_agent_advisor_policy.live import PolicyLive
from dd_agent_advisor_policy.opf import OpenPolicyFinder
from dd_agent_advisor_policy.ror import RorDump, RorLive
from dd_agent_advisor_policy.snapshot import PolicySnapshot
from dd_sdk import serve
from dd_sdk.credentials import ConfigError, api_key
from dd_sdk.model import declared
from dd_sdk.model_provider import optional_model

SWITCH = "DD_POLICY_ADVISOR"
OLD_SWITCH = "DD_POLICY_EXPLAINER"
OPF_KEY = "OPEN_POLICY_FINDER_API_KEY"


def _switch(env: Mapping[str, str]) -> Mapping[str, str]:
    """`env` with the older switch's value under the new name, when only the older is set."""
    if (env.get(SWITCH) or "").strip() or not (env.get(OLD_SWITCH) or "").strip():
        return env
    return {**env, SWITCH: env[OLD_SWITCH]}


def _lookups(env: Mapping[str, str]) -> int:
    raw = (env.get("DD_POLICY_MAX_LOOKUPS") or "").strip()
    if not raw:
        return DEFAULT_MAX_LOOKUPS
    try:
        value = int(raw)
    except ValueError:
        value = -1
    if not 0 <= value <= 30:
        raise ConfigError(f"DD_POLICY_MAX_LOOKUPS={raw!r}: expected a whole number from 0 to 30")
    return value


def build_explainer(env: Mapping[str, str]) -> Explainer:
    env = _switch(env)
    model = optional_model(env, SWITCH, default_model=DEFAULT_MODEL, default="model", tool_use=True)
    return TemplateExplainer() if model is None else ModelAdvisor(model, _lookups(env))


def build_opf(env: Mapping[str, str]) -> OpenPolicyFinder | None:
    if not ((env.get(OPF_KEY) or "").strip() or (env.get(f"{OPF_KEY}_FILE") or "").strip()):
        return None
    return OpenPolicyFinder(api_key(env, OPF_KEY))


def build_crossref(env: Mapping[str, str]) -> CrossrefJournals | None:
    choice = (env.get("DD_POLICY_CROSSREF") or "live").strip()
    if choice not in ("live", "off"):
        raise ConfigError(f"DD_POLICY_CROSSREF={choice!r}: expected live or off")
    return CrossrefJournals() if choice == "live" else None


def build(env: Mapping[str, str] | None = None) -> PolicyAgent:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    explainer = build_explainer(env)
    ror_choice = env.get("DD_POLICY_ROR", "snapshot")
    if ror_choice not in ("snapshot", "live"):
        raise ConfigError(f"DD_POLICY_ROR={ror_choice!r}: expected snapshot or live")
    opf, crossref = build_opf(env), build_crossref(env)
    choice = env.get("DD_POLICY_RETRIEVAL", "snapshot")
    if choice == "snapshot":
        agent = PolicyAgent(PolicySnapshot(), explainer, opf=opf, crossref=crossref)
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
            PolicyLive(login=login, password=password),
            explainer,
            fallback=PolicySnapshot(),
            opf=opf,
            crossref=crossref,
        )
    else:
        raise ConfigError(f"DD_POLICY_RETRIEVAL={choice!r}: expected snapshot or live")
    if ror_choice == "live":
        agent.organisations, agent.organisations_fallback = RorLive(), RorDump()
    else:
        agent.organisations = RorDump()
    if isinstance(explainer, ModelAdvisor):
        agent.spec = replace(agent.spec, models=(declared(explainer.model),))
    return agent


def main() -> int:
    """Console script: serve the policy advisor over A2A (`dd_sdk.serve`)."""
    return serve.main(build)

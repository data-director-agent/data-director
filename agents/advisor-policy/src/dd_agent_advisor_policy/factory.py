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
- Journals are identified in Crossref's public API (`journals.py`), which needs no account. Whether
  they are is the agent's `journals` setting, which a deployment's institutional profile sets
  (`agent_settings`, docs/specs/policy-and-identity.md), not an environment variable.
- Each policy's own text is read with the model the agent's settings configure
  (`DD_MODEL_PROVIDER`, `DD_MODEL_ID` and the provider's key, as below), whether or not it also
  explains. With no usable model, the text is not read and the statement says so. Whether it is
  read at all is the agent's `policy_text` setting, which the profile sets.
- `DD_POLICY_EXPLAINER`: `template` (default) or `model`, which has a model write the rationale
  (`anthropic`, its older name, still works).
- With `model`: `DD_MODEL_PROVIDER` (`anthropic` by default), `DD_MODEL_ID` (Claude Sonnet 5.5
  by default for Anthropic), `DD_MODEL_BASE_URL` and the provider's key, read at start-up
  (`dd_sdk.model_provider`, docs/specs/policy-and-identity.md).

An unknown value, live retrieval with no account, or an unusable model setting is a
configuration error (`ConfigError`), and `dd-advisor-policy serve` stops at start-up. The spec
declares each model it sends data to (`AgentSpec.models`).
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
from dd_agent_advisor_policy.extract import Extractor, ModelExtractor, NoExtractor
from dd_agent_advisor_policy.journals import CrossrefJournals
from dd_agent_advisor_policy.live import PolicyLive
from dd_agent_advisor_policy.policy_text import PolicyPages
from dd_agent_advisor_policy.ror import RorDump, RorLive
from dd_agent_advisor_policy.snapshot import PolicySnapshot
from dd_sdk import serve
from dd_sdk.credentials import ConfigError, api_key
from dd_sdk.model import Model, declared
from dd_sdk.model_provider import configured_model, optional_model


def build_explainer(env: Mapping[str, str]) -> Explainer:
    model = optional_model(env, "DD_POLICY_EXPLAINER", default_model=DEFAULT_MODEL)
    return TemplateExplainer() if model is None else ModelExplainer(model)


def build_extractor(env: Mapping[str, str], explainer: Explainer) -> Extractor:
    """The explainer's model, if it has one; otherwise whichever model the settings configure;
    otherwise none, and the policies' text is not read. A model that cannot be configured here is
    not an error: reading the text only adds to what the records say."""
    if isinstance(explainer, ModelExplainer):
        return ModelExtractor(explainer.model)
    try:
        model: Model = configured_model(env, default_model=DEFAULT_MODEL)
    except ConfigError:
        return NoExtractor()
    return ModelExtractor(model)


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
    agent.journals = CrossrefJournals()
    agent.pages = PolicyPages()
    agent.extractor = build_extractor(env, explainer)
    models = [
        m.model
        for m in (explainer, agent.extractor)
        if isinstance(m, ModelExplainer | ModelExtractor)
    ]
    uses = tuple(dict.fromkeys(declared(m) for m in models))
    if uses:
        agent.spec = replace(agent.spec, models=uses)
    return agent


def main() -> int:
    """Console script: serve the policy advisor over A2A (`dd_sdk.serve`)."""
    return serve.main(build)

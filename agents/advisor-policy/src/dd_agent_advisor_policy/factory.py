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
- Each policy's own text is read with the model the agent's settings configure, whether or not
  the advisor also uses one. With no usable model, the text is not read and the statement says so.
  Whether it is read at all is the agent's `policy_text` setting, which the profile sets
  (`agent_settings`, docs/specs/policy-and-identity.md).
- The model's provider, id and key: as for every advisor (docs/guide/operations/ai-models.md).

An unknown value, live retrieval with no account, or an unusable model setting is a
configuration error (`ConfigError`), and `dd-advisor-policy serve` stops at start-up: with the
setting unset and no model key, the error says to set `DD_POLICY_ADVISOR=template` to run without
a model. With the model advisor the spec declares the model it sends registry text to, and that
it relies on tool calls (`AgentSpec.models`).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import replace

from dd_agent_advisor_policy.advise import DEFAULT_MAX_LOOKUPS, DEFAULT_MODEL, ModelAdvisor
from dd_agent_advisor_policy.agent import PolicyAgent
from dd_agent_advisor_policy.crossref import CrossrefJournals
from dd_agent_advisor_policy.explain import Explainer, TemplateExplainer
from dd_agent_advisor_policy.extract import Extractor, ModelExtractor, NoExtractor
from dd_agent_advisor_policy.live import PolicyLive
from dd_agent_advisor_policy.opf import OpenPolicyFinder
from dd_agent_advisor_policy.policy_text import PolicyPages
from dd_agent_advisor_policy.retrieve import Policies
from dd_agent_advisor_policy.ror import RorDump, RorLive
from dd_agent_advisor_policy.search import Sources
from dd_agent_advisor_policy.snapshot import PolicySnapshot
from dd_sdk import serve
from dd_sdk.credentials import ConfigError, api_key
from dd_sdk.model import Model, declared
from dd_sdk.model_provider import configured_model, optional_model
from dd_sdk.registry.fairsharing import FairsharingClient

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
    model = optional_model(env, SWITCH, default_model=DEFAULT_MODEL, tool_use=True)
    return TemplateExplainer() if model is None else ModelAdvisor(model, _lookups(env))


def build_extractor(env: Mapping[str, str], explainer: Explainer) -> Extractor:
    """The advisor's model, if it has one; otherwise whichever model the settings configure;
    otherwise none, and the policies' text is not read. A model that cannot be configured here is
    not an error: reading the text only adds to what the records say."""
    if isinstance(explainer, ModelAdvisor):
        return ModelExtractor(explainer.model)
    try:
        model: Model = configured_model(env, default_model=DEFAULT_MODEL)
    except ConfigError:
        return NoExtractor()
    return ModelExtractor(model)


def build_opf(env: Mapping[str, str]) -> OpenPolicyFinder | None:
    """Open Policy Finder with its key, or None with a warning at start-up: without it, funders'
    and journals' policies cannot be checked, and a run says so (#1319)."""
    if not ((env.get(OPF_KEY) or "").strip() or (env.get(f"{OPF_KEY}_FILE") or "").strip()):
        logging.getLogger(__name__).warning(
            "%s is not set: funders' and journals' open access policies will not be checked, "
            "and a run that needs them reports that it could not search",
            OPF_KEY,
        )
        return None
    return OpenPolicyFinder(api_key(env, OPF_KEY))


def build_crossref(env: Mapping[str, str]) -> CrossrefJournals | None:
    choice = (env.get("DD_POLICY_CROSSREF") or "live").strip()
    if choice not in ("live", "off"):
        raise ConfigError(f"DD_POLICY_CROSSREF={choice!r}: expected live or off")
    return CrossrefJournals() if choice == "live" else None


def build_policies(env: Mapping[str, str]) -> tuple[Policies, Policies | None]:
    """FAIRsharing's policy records, from `DD_POLICY_RETRIEVAL`: the pinned snapshot, or the live
    search with the snapshot standing in when it is down."""
    choice = env.get("DD_POLICY_RETRIEVAL", "snapshot")
    if choice == "snapshot":
        return PolicySnapshot(), None
    if choice != "live":
        raise ConfigError(f"DD_POLICY_RETRIEVAL={choice!r}: expected snapshot or live")
    login = env.get("FAIRSHARING_LOGIN")
    if not (login and (env.get("FAIRSHARING_PASSWORD") or env.get("FAIRSHARING_PASSWORD_FILE"))):
        raise ConfigError(
            "DD_POLICY_RETRIEVAL=live: FAIRsharing search needs FAIRSHARING_LOGIN and "
            "FAIRSHARING_PASSWORD (or FAIRSHARING_PASSWORD_FILE)"
        )
    # Read as a credential, so the password may be a file under $CREDENTIALS_DIRECTORY.
    password = api_key(env, "FAIRSHARING_PASSWORD")
    api = FairsharingClient.from_env(env, login=login, password=password, follow_redirects=True)
    return PolicyLive(api=api), PolicySnapshot()


def ror_choice(env: Mapping[str, str]) -> str:
    choice = env.get("DD_POLICY_ROR", "snapshot")
    if choice not in ("snapshot", "live"):
        raise ConfigError(f"DD_POLICY_ROR={choice!r}: expected snapshot or live")
    return choice


def build(env: Mapping[str, str] | None = None) -> PolicyAgent:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    explainer = build_explainer(env)
    ror = ror_choice(env)
    opf, crossref = build_opf(env), build_crossref(env)
    policies, fallback = build_policies(env)
    sources = Sources(
        policies=policies,
        fallback=fallback,
        organisations=RorLive() if ror == "live" else RorDump(),
        organisations_fallback=RorDump() if ror == "live" else None,
        opf=opf,
        crossref=crossref,
    )
    extractor = build_extractor(env, explainer)
    agent = PolicyAgent(sources, explainer, pages=PolicyPages(), extractor=extractor)
    models = [
        m.model for m in (explainer, extractor) if isinstance(m, ModelAdvisor | ModelExtractor)
    ]
    uses = tuple(dict.fromkeys(declared(m) for m in models))
    if uses:
        agent.spec = replace(agent.spec, models=uses)
    return agent


def main() -> int:
    """Console script: serve the policy advisor over A2A (`dd_sdk.serve`)."""
    return serve.main(build)

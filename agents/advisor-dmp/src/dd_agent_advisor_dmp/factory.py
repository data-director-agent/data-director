"""Factory and console script for advisor.dmp (R8).

`build` assembles the Data Management Plan Checker from its own environment variables (documented
in `config/examples/agents.env`):

- `DD_DMP_MATCHER`: `template` (default) matches by rule alone, calls no model and needs no key.
  `model` has a model read what the rules leave over (`match.py`); `anthropic` names the same
  while `DD_MODEL_PROVIDER` is `anthropic`.
- With `model`: `DD_MODEL_PROVIDER` (`anthropic` by default), `DD_MODEL_ID` (Claude Sonnet 5.5
  by default for Anthropic), `DD_MODEL_BASE_URL` and the provider's key, read at start-up
  (`dd_sdk.model_provider`, docs/specs/policy-and-identity.md).

An unknown value, or an unusable model setting, is a configuration error (`ConfigError`).
`dd-advisor-dmp serve` then stops at start-up instead of serving something other than what was
configured. With a model the spec declares the model it sends data to (`AgentSpec.models`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace

from dd_agent_advisor_dmp.agent import DmpChecker
from dd_agent_advisor_dmp.match import DEFAULT_MODEL, Matcher, ModelMatcher, TemplateMatcher
from dd_sdk import serve
from dd_sdk.model import declared
from dd_sdk.model_provider import optional_model

SWITCH = "DD_DMP_MATCHER"


def build_matcher(env: Mapping[str, str]) -> Matcher:
    model = optional_model(env, SWITCH, default_model=DEFAULT_MODEL)
    return TemplateMatcher() if model is None else ModelMatcher(model)


def build(env: Mapping[str, str] | None = None) -> DmpChecker:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    agent = DmpChecker(build_matcher(env))
    if isinstance(agent.matcher, ModelMatcher):
        agent.spec = replace(agent.spec, models=(declared(agent.matcher.model),))
    return agent


def main() -> int:
    """The `dd-advisor-dmp` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)

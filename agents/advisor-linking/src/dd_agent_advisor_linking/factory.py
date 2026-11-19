"""Factory and console script for advisor.linking.

`build` assembles the Linking Adviser from its own environment variables (documented in
`config/examples/agents.env`):

- `DD_LINKING_SUMMARISER`: `model` (the default) has a model write a short summary beside the rules'
  findings (`dd_sdk.summary`); `template` gives the rules' own summary, calls no model and needs
  no key. Each link is recognised, checked and looked up by rule either way.
- With `model`: `DD_MODEL_PROVIDER` (`anthropic` by default), `DD_MODEL_ID` (Claude Sonnet 5.5
  by default for Anthropic), `DD_MODEL_BASE_URL` and the provider's key, read at start-up
  (`dd_sdk.model_provider`, docs/specs/policy-and-identity.md).

An unknown value, or an unusable model setting, is a configuration error (`ConfigError`).
`dd-advisor-linking serve` then stops at start-up instead of serving something other than what
was configured. With a model the spec declares the model it sends data to (`AgentSpec.models`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Literal

from dd_agent_advisor_linking.agent import LinkingAdviser
from dd_sdk import serve, summary

SWITCH = "DD_LINKING_SUMMARISER"
DEFAULT: Literal["template", "model"] = "model"
DEFAULT_MODEL = "claude-sonnet-5-5"
# What the model is told it may and may not do; the prose is a Markdown file beside this module.
SYSTEM_PROMPT = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8").strip()


def build(env: Mapping[str, str] | None = None) -> LinkingAdviser:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    summariser = summary.configured(
        env, SWITCH, SYSTEM_PROMPT, default_model=DEFAULT_MODEL, default=DEFAULT
    )
    agent = LinkingAdviser(summariser=summariser)
    agent.spec = replace(agent.spec, models=summary.declared_models(summariser))
    return agent


def main() -> int:
    """The `dd-advisor-linking` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)

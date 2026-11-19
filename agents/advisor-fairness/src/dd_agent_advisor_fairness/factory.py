"""Factory and console script for advisor.fairness.

`build` assembles the FAIR Assessor from its own environment variables (documented in
`config/examples/agents.env`):

- `DD_FAIRNESS_WRITER`: `template` (default) gives the rule table's own recommendation for each
  unmet check, calls no model and needs no key. `model` has a model tailor each recommendation to
  the record as given (`write.py`); `anthropic` names the same while `DD_MODEL_PROVIDER` is
  `anthropic`. Whether a check is met is decided by rule either way.
- With `model`: `DD_MODEL_PROVIDER` (`anthropic` by default), `DD_MODEL_ID` (Claude Sonnet 5.5
  by default for Anthropic), `DD_MODEL_BASE_URL` and the provider's key, read at start-up
  (`dd_sdk.model_provider`, docs/specs/policy-and-identity.md).

An unknown value, or an unusable model setting, is a configuration error (`ConfigError`).
`dd-advisor-fairness serve` then stops at start-up instead of serving something other than what
was configured. With a model the spec declares the model it sends data to (`AgentSpec.models`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from typing import Literal

from dd_agent_advisor_fairness.agent import FairAssessor
from dd_agent_advisor_fairness.write import DEFAULT_MODEL, ModelWriter, TemplateWriter, Writer
from dd_sdk import serve
from dd_sdk.model import declared
from dd_sdk.model_provider import optional_model

SWITCH = "DD_FAIRNESS_WRITER"
DEFAULT: Literal["template", "model"] = "template"


def build_writer(env: Mapping[str, str]) -> Writer:
    model = optional_model(env, SWITCH, default_model=DEFAULT_MODEL, default=DEFAULT)
    return TemplateWriter() if model is None else ModelWriter(model)


def build(env: Mapping[str, str] | None = None) -> FairAssessor:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    agent = FairAssessor(build_writer(env))
    if isinstance(agent.writer, ModelWriter):
        agent.spec = replace(agent.spec, models=(declared(agent.writer.model),))
    return agent


def main() -> int:
    """The `dd-advisor-fairness` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)

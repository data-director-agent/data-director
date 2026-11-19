"""Factory and console script for advisor.rights.

`build` assembles the Rights and Licensing Adviser from its own environment variables (documented
in `config/examples/agents.env`):

- `DD_RIGHTS_INTERPRETER`: `template` reads the reuse wanted only as one of the table's values,
  calls no model and needs no key. `model` (the default) has a model read what the rules cannot: a
  reuse wish in the researcher's own words, and questions tailored to third-party content or a
  mandate (`interpret.py`); `anthropic` names the same while `DD_MODEL_PROVIDER` is `anthropic`.
- With `model`: `DD_MODEL_PROVIDER` (`anthropic` by default), `DD_MODEL_ID` (Claude Sonnet 5.5
  by default for Anthropic), `DD_MODEL_BASE_URL` and the provider's key, read at start-up
  (`dd_sdk.model_provider`, docs/specs/policy-and-identity.md).

An unknown value, or an unusable model setting, is a configuration error (`ConfigError`).
`dd-advisor-rights serve` then stops at start-up instead of serving something other than what was
configured. With a model the spec declares the model it sends data to (`AgentSpec.models`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from typing import Literal

from dd_agent_advisor_rights.agent import RightsAdviser
from dd_agent_advisor_rights.interpret import (
    DEFAULT_MODEL,
    Interpreter,
    ModelInterpreter,
    TemplateInterpreter,
)
from dd_sdk import serve
from dd_sdk.model import declared
from dd_sdk.model_provider import optional_model

SWITCH = "DD_RIGHTS_INTERPRETER"
DEFAULT: Literal["template", "model"] = "model"


def build_interpreter(env: Mapping[str, str]) -> Interpreter:
    model = optional_model(env, SWITCH, default_model=DEFAULT_MODEL, default=DEFAULT)
    return TemplateInterpreter() if model is None else ModelInterpreter(model)


def build(env: Mapping[str, str] | None = None) -> RightsAdviser:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    agent = RightsAdviser(interpreter=build_interpreter(env))
    if isinstance(agent.interpreter, ModelInterpreter):
        agent.spec = replace(agent.spec, models=(declared(agent.interpreter.model),))
    return agent


def main() -> int:
    """The `dd-advisor-rights` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)

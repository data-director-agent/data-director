"""Factory and console script for advisor.ethics.

`build` assembles the Research Ethics Adviser from its own environment variables (documented in
`config/examples/agents.env`):

- `DD_ETHICS_READER`: `model` (default) has a model read the field names as well as the keyword
  table; it may add flags and questions but never remove a keyword flag (`anthropic`, its older
  name, still works). `template` matches field names by keyword only and needs no key.
- The model's provider, id and key: as for every advisor (docs/guide/operations/ai-models.md).

An unknown value, or an unusable model setting, is a configuration error (`ConfigError`).
`dd-advisor-ethics serve` then stops at start-up instead of serving something other than what was
configured: with the setting unset and no model key, the error says to set
`DD_ETHICS_READER=template` to run without a model. With the model reader the spec declares the
model it sends the field names to (`AgentSpec.models`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace

from dd_agent_advisor_ethics.agent import EthicsAdviser
from dd_agent_advisor_ethics.reader import DEFAULT_MODEL, ModelReader, Reader, TemplateReader
from dd_sdk import serve
from dd_sdk.model import declared
from dd_sdk.model_provider import optional_model

SWITCH = "DD_ETHICS_READER"


def build_reader(env: Mapping[str, str]) -> Reader:
    model = optional_model(env, SWITCH, default_model=DEFAULT_MODEL)
    return TemplateReader() if model is None else ModelReader(model)


def build(env: Mapping[str, str] | None = None) -> EthicsAdviser:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    agent = EthicsAdviser(reader=build_reader(env))
    if isinstance(agent.reader, ModelReader):
        agent.spec = replace(agent.spec, models=(declared(agent.reader.model),))
    return agent


def main() -> int:
    """The `dd-advisor-ethics` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)

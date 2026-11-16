"""Factory and console script for the Documentation Editor.

`build` assembles the agent from its own environment variables (documented in
`config/examples/agents.env`):

- `DD_DOCUMENTATION_WRITER`: `model` (default), which has a model write the README's prose and
  suggest answers to the draft's questions from the project's facts (`prose.py`), or `template`,
  which writes no prose and suggests nothing, and needs no key. `anthropic`, the older name for
  `model`, still works.
- With `model`: `DD_MODEL_PROVIDER` (`anthropic` by default), `DD_MODEL_ID` (Claude Sonnet 5.5
  by default for Anthropic), `DD_MODEL_BASE_URL` and the provider's key, read at start-up
  (`dd_sdk.model_provider`, docs/specs/policy-and-identity.md).

An unknown value, or an unusable model setting, is a configuration error (`ConfigError`), and
`dd-advisor-documentation serve` stops at start-up: with the setting unset and no key, the error
says to set `DD_DOCUMENTATION_WRITER=template` to run without a model. With the model writer the
spec declares the model it sends the project's facts to, and whether it is hosted
(`AgentSpec.models`), which is what the profile's rules on project content for hosted models
read (docs/specs/projects.md, invariant 8).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace

from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_documentation.prose import (
    DEFAULT_MODEL,
    ModelWriter,
    TemplateWriter,
    Writer,
)
from dd_sdk import serve
from dd_sdk.model import declared
from dd_sdk.model_provider import optional_model


def build_writer(env: Mapping[str, str]) -> Writer:
    model = optional_model(
        env, "DD_DOCUMENTATION_WRITER", default_model=DEFAULT_MODEL, default="model"
    )
    return TemplateWriter() if model is None else ModelWriter(model)


def build(env: Mapping[str, str] | None = None) -> DocumentationEditor:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    writer = build_writer(env)
    agent = DocumentationEditor(writer=writer)
    if isinstance(writer, ModelWriter):
        agent.spec = replace(agent.spec, models=(declared(writer.model),))
    return agent


def main() -> int:
    """The `dd-advisor-documentation` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)

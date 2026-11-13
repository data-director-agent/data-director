"""Factory and console script for the Documentation Editor.

`build` assembles the agent from its own environment variables (documented in
`config/examples/agents.env`):

- `DD_DOCUMENTATION_WRITER`: `template` (default), which writes no prose, or `anthropic`, which
  has a model write the README's prose from the project's facts (`prose.py`).
- `DD_MODEL_ID`: the model the Anthropic writer calls.
- `ANTHROPIC_API_KEY` (development) or `ANTHROPIC_API_KEY_FILE` (deployment): the Anthropic
  writer's key, read at start-up (`dd_sdk.credentials`, docs/specs/policy-and-identity.md).

An unknown value, or the Anthropic writer with no key, is a configuration error (`ConfigError`),
and `dd-advisor-documentation serve` stops at start-up. With the Anthropic writer the spec declares
the model it sends the project's facts to (`AgentSpec.models`), which is what the profile's rules
on project content for hosted models read (docs/specs/projects.md, invariant 8).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace

from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_documentation.prose import (
    DEFAULT_MODEL,
    PROVIDER,
    AnthropicWriter,
    TemplateWriter,
    Writer,
)
from dd_sdk import serve
from dd_sdk.agent import ModelUse
from dd_sdk.credentials import ConfigError, model_endpoint


def build_writer(env: Mapping[str, str]) -> Writer:
    choice = env.get("DD_DOCUMENTATION_WRITER", "template")
    if choice == "template":
        return TemplateWriter()
    if choice == "anthropic":
        return AnthropicWriter(
            model_id=env.get("DD_MODEL_ID", DEFAULT_MODEL), endpoint=model_endpoint(env)
        )
    raise ConfigError(f"DD_DOCUMENTATION_WRITER={choice!r}: expected template or anthropic")


def build(env: Mapping[str, str] | None = None) -> DocumentationEditor:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    writer = build_writer(env)
    agent = DocumentationEditor(writer=writer)
    if writer.model_id:
        agent.spec = replace(agent.spec, models=(ModelUse(PROVIDER, writer.model_id, "hosted"),))
    return agent


def main() -> int:
    """The `dd-advisor-documentation` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)

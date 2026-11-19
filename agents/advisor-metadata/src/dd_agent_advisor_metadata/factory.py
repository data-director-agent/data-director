"""Factory and console script for advisor.metadata.

`build` assembles the Metadata Librarian from its own environment variables (documented in
`config/examples/agents.env`):

- `DD_METADATA_SUGGESTER`: `template` drafts the record and its questions by rule, suggests nothing,
  calls no model and needs no key. `model` (the default) also has a model suggest values for some of
  the questions, beside the question and never in the record (`suggest.py`); `anthropic` names the
  same while `DD_MODEL_PROVIDER` is `anthropic`.
- With `model`: `DD_MODEL_PROVIDER` (`anthropic` by default), `DD_MODEL_ID` (Claude Sonnet 5.5
  by default for Anthropic), `DD_MODEL_BASE_URL` and the provider's key, read at start-up
  (`dd_sdk.model_provider`, docs/specs/policy-and-identity.md).

An unknown value, or an unusable model setting, is a configuration error (`ConfigError`), and
`dd-advisor-metadata serve` stops at start-up instead of serving something other than what was
configured. With a model the spec declares the model it sends the project's facts to, and whether
it is hosted (`AgentSpec.models`), which is what the profile's rules on project content for
hosted models read (docs/specs/projects.md, invariant 8).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from typing import Literal

from dd_agent_advisor_metadata.agent import MetadataLibrarian
from dd_agent_advisor_metadata.suggest import (
    DEFAULT_MODEL,
    ModelSuggester,
    Suggester,
    TemplateSuggester,
)
from dd_sdk import serve
from dd_sdk.model import declared
from dd_sdk.model_provider import optional_model

SWITCH = "DD_METADATA_SUGGESTER"
DEFAULT: Literal["template", "model"] = "model"


def build_suggester(env: Mapping[str, str]) -> Suggester:
    model = optional_model(env, SWITCH, default_model=DEFAULT_MODEL, default=DEFAULT)
    return TemplateSuggester() if model is None else ModelSuggester(model)


def build(env: Mapping[str, str] | None = None) -> MetadataLibrarian:
    """The factory `main` serves. `env` defaults to the process environment."""
    env = os.environ if env is None else env
    suggester = build_suggester(env)
    agent = MetadataLibrarian(suggester=suggester)
    if isinstance(suggester, ModelSuggester):
        agent.spec = replace(agent.spec, models=(declared(suggester.model),))
    return agent


def main() -> int:
    """The `dd-advisor-metadata` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)

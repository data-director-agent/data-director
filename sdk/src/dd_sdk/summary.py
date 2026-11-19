"""Summarisers: a short summary, in plain language, of what an agent's rules already found.

The barebones model path of an advisor whose work is otherwise exact (docs/specs/agents.md,
Model-backed personas): its rules decide every finding, and a summariser writes one summary beside
them. It cannot add, remove or change a finding, so the summary is the only value a model writes.

- `TemplateSummariser` gives the rules' own summary (`Findings.template`) and needs no
  credentials. It is the path an operator selects to run the agent with no model.
- `ModelSummariser` sends the model the findings as JSON and asks for one summary line, through
  `dd_sdk.explain.ModelExplainer`, so the call is recorded as every other model call is. A reply
  that is missing, refused or names a DOI, ORCID iD or web address the findings do not give is
  replaced by the template, marked `template`, and the replacement is said in the text.

`summarise` runs either and falls back on the template when the model cannot be reached;
`with_calls` puts the model calls it made on the agent's result. `configured` builds the
summariser an agent's settings choose, and `declared_models` what its card declares; `factory`
makes an agent package's `build` and `main` from both.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, Protocol

from dd_sdk import serve
from dd_sdk.agent import Agent, ModelUse, RunContext
from dd_sdk.agent_result import AgentResult
from dd_sdk.contract.models import Derivation
from dd_sdk.explain import Explanation, ModelExplainer, Rationale, TemplateExplainer
from dd_sdk.model import Model, ModelCallError, Usage, declared
from dd_sdk.model_provider import optional_model

# The identifiers a summary may name only if the findings give them: a DOI, an ORCID iD and any
# web address. The last character is not punctuation, so a sentence's full stop is not part of it.
KINDS = (
    r"https?://[^\s\"'<>()]*[^\s\"'<>().,;:]",
    r"\b10\.\d{4,9}/[^\s\"'<>()]*[^\s\"'<>().,;:]",
    r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b",
)
IDENTIFIER = re.compile("|".join(KINDS), re.IGNORECASE)
# The model a summariser calls when the agent's settings name none, for Anthropic.
DEFAULT_MODEL = "claude-sonnet-5-5"
UNREACHABLE = " (The model could not be reached; template used.)"
REPLY_FORMAT = (
    "Reply with exactly one line: `1. ` followed by the summary, in at most three sentences."
)


@dataclass(frozen=True)
class Findings:
    """What a summariser is told: the input and the rules' findings, as JSON-ready values, and
    the rules' own summary, used whenever the model's is not."""

    findings: Mapping[str, Any]
    template: str


class Summariser(Protocol):
    model_id: str | None

    def explain(
        self, context: None, items: list[Findings], ctx: RunContext, lookups: object | None = None
    ) -> Explanation: ...


class TemplateSummariser(TemplateExplainer[None, Findings]):
    """The rules' own summary."""

    def rationale(self, item: Findings) -> str:
        return item.template


class ModelSummariser(ModelExplainer[None, Findings]):
    """Summarises with the model the agent's settings name (`dd_sdk.model_provider`), or a
    `dd_sdk.testing.FakeModel` in tests. `system_prompt` is the agent's own, from the
    `system_prompt.md` beside the module that builds it."""

    pattern = IDENTIFIER

    def __init__(self, model: Model, system_prompt: str) -> None:
        super().__init__(model)
        self.system_prompt = system_prompt

    def prompt(self, context: None, items: list[Findings]) -> str:
        (item,) = items
        return f"{json.dumps(item.findings, ensure_ascii=False, indent=2)}\n\n{REPLY_FORMAT}"

    def template(self, item: Findings) -> str:
        return item.template

    def allowed(self, items: list[Findings]) -> set[str]:
        """The identifiers the findings themselves give, each kind found on its own, so that a DOI
        given within its web address may be named on its own too."""
        given = json.dumps([item.findings for item in items], ensure_ascii=False)
        return {
            found.casefold() for kind in KINDS for found in re.findall(kind, given, re.IGNORECASE)
        }


def summarise(
    summariser: Summariser, findings: Findings, ctx: RunContext
) -> tuple[Rationale, Explanation]:
    """The summary, and the explanation it came from (its tokens and model calls). The template,
    saying why, when the model cannot be reached."""
    try:
        explanation = summariser.explain(None, [findings], ctx)
    except ModelCallError:
        summary = Rationale(findings.template + UNREACHABLE, Derivation.TEMPLATE)
        return summary, Explanation([summary], Usage())
    return explanation.rationales[0], explanation


def with_calls(result: AgentResult, model_id: str | None, explanation: Explanation) -> AgentResult:
    """`result` with the model, the tokens and the calls of the summary's `explanation`."""
    calls = explanation.calls
    return replace(
        result,
        model_id=model_id,
        input_tokens=explanation.usage.input_tokens,
        output_tokens=explanation.usage.output_tokens,
        model_calls=tuple(calls.calls) if calls is not None else (),
        prompts=calls.prompts if calls is not None else {},
    )


def configured(
    env: Mapping[str, str],
    setting: str,
    system_prompt: str,
    *,
    default_model: str,
    default: Literal["template", "model"] = "model",
) -> Summariser:
    """The summariser `env[setting]` chooses (`dd_sdk.model_provider.optional_model`): a model's,
    by default, or the template's."""
    model = optional_model(env, setting, default_model=default_model, default=default)
    return TemplateSummariser() if model is None else ModelSummariser(model, system_prompt)


def declared_models(summariser: Summariser) -> tuple[ModelUse, ...]:
    """The model a summariser sends data to, for `AgentSpec.models`; none for the template."""
    return (declared(summariser.model),) if isinstance(summariser, ModelSummariser) else ()


class Summarised(Agent, Protocol):
    """An agent whose rules decide its findings and whose summariser is given to it."""

    def __init__(self, *, summariser: Summariser) -> None: ...


def factory[A: Summarised](
    agent: type[A],
    setting: str,
    system_prompt: Path,
    *,
    default_model: str = DEFAULT_MODEL,
    default: Literal["template", "model"] = "model",
) -> tuple[Callable[[Mapping[str, str] | None], A], Callable[[], int]]:
    """An agent package's `build` and console-script `main`, for its `factory` module.

    `build(env)` reads `env` (the process environment by default) for `setting`, `default` unless it
    says otherwise, and the model settings `dd_sdk.model_provider` reads; gives the agent the
    summariser they choose, with the system prompt read from `system_prompt`; and declares on its
    card the model it sends data to. A setting that cannot be used is a `ConfigError`, so `main`
    stops at start-up instead of serving something other than what was configured."""

    def build(env: Mapping[str, str] | None = None) -> A:
        env = os.environ if env is None else env
        prompt = system_prompt.read_text(encoding="utf-8").strip()
        summariser = configured(env, setting, prompt, default_model=default_model, default=default)
        made = agent(summariser=summariser)
        made.spec = replace(made.spec, models=declared_models(summariser))
        return made

    def main() -> int:
        return serve.main(lambda: build(None))

    return build, main

"""Explainers: turn what an agent's rules already decided into rationale (Blueprint P8, C14).

An explainer receives items that were retrieved, assessed and ranked before it is called, and
returns one rationale per item, in order. It cannot add, remove or reorder items, nor change a
judgement; an agent that lets a model add something (a policy it found, a recommendation) checks
the addition itself and says so on its own `Explanation` subclass.

- `TemplateExplainer` writes each rationale from the agent's fixed template, and needs no
  credentials. Every model-backed agent keeps it as the path an operator can select, and falls
  back on it whenever the model cannot answer.
- `ModelExplainer` asks a model for one numbered rationale per item, in one call, and uses the
  template for any item whose line is missing or names an identifier it was not given.

A model's rationale that names a registry identifier it was not given is replaced by the
template, and the replacement is said in the text (`checked_rationale`).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from dd_sdk.agent import RunContext
from dd_sdk.contract.models import Derivation
from dd_sdk.model import Model, Usage, call
from dd_sdk.prompts import ModelCallLog

UNGROUNDED = " (Model rationale replaced: ungrounded reference.)"
MISSING = " (No model rationale; template used.)"
DECLINED = " (Model declined; template used.)"


@dataclass(frozen=True)
class Rationale:
    text: str
    derivation: Derivation


@dataclass(frozen=True)
class Explanation:
    """One rationale per item, and the tokens spent. Returned rather than kept on the explainer,
    because one explainer serves concurrent runs (`dd_sdk.serve` runs each request on its own
    thread). An agent whose explainer may say more subclasses it."""

    rationales: list[Rationale]
    usage: Usage
    # The model calls made and the prompts sent (dd_sdk.prompts); None if no model was called.
    calls: ModelCallLog | None = None


def add_usage(a: Usage, b: Usage) -> Usage:
    """The tokens of two calls together; a count neither provider reported stays None."""

    def add(x: int | None, y: int | None) -> int | None:
        return None if x is None and y is None else (x or 0) + (y or 0)

    return Usage(add(a.input_tokens, b.input_tokens), add(a.output_tokens, b.output_tokens))


def names_other_identifier(text: str, allowed: Collection[str], pattern: re.Pattern[str]) -> bool:
    """Whether `text` names an identifier, as `pattern` finds them, outside `allowed`. Case is
    ignored."""
    wanted = {a.casefold() for a in allowed}
    return any(m.casefold() not in wanted for m in pattern.findall(text))


def checked_rationale(
    text: str, allowed: Collection[str], pattern: re.Pattern[str], fallback: str
) -> Rationale:
    """A model's rationale, with its whitespace tidied; or `fallback`, marked as a replacement,
    if it names an identifier outside `allowed`."""
    if names_other_identifier(text, allowed, pattern):
        return Rationale(fallback + UNGROUNDED, Derivation.TEMPLATE)
    return Rationale(" ".join(text.split()), Derivation.MODEL)


def missing_rationale(fallback: str) -> Rationale:
    """The template, for an item the model gave no rationale for."""
    return Rationale(fallback + MISSING, Derivation.TEMPLATE)


def with_reason(rationales: Sequence[Rationale], why: str) -> list[Rationale]:
    """Template rationales used in place of a model's, each saying why."""
    return [Rationale(r.text + f" ({why}; template used.)", r.derivation) for r in rationales]


class TemplateExplainer[C, I]:
    """Writes each item's rationale from the agent's template (`rationale`)."""

    model_id: str | None = None

    def rationale(self, item: I) -> str:
        raise NotImplementedError

    def explain(
        self, context: C, items: list[I], ctx: RunContext, lookups: object | None = None
    ) -> Explanation:
        return Explanation(
            [Rationale(self.rationale(item), Derivation.TEMPLATE) for item in items], Usage()
        )


_NUMBERED = re.compile(r"\s*(\d+)[.)]\s+(.*\S)")


class ModelExplainer[C, I]:
    """Explains with one call to the model the agent's settings name (`dd_sdk.model_provider`),
    through `dd_sdk.model.call`, which records its `chat` span, its tokens and its prompt.

    The model is sent `system_prompt` and `prompt(context, items)`, and answers one numbered line
    per item. An agent subclasses it and says how to write the prompt, the template rationale,
    which identifiers each run may name (`allowed`) and how to find one (`pattern`)."""

    system_prompt: str
    pattern: re.Pattern[str]

    def __init__(self, model: Model) -> None:
        self.model = model
        self.model_id: str | None = model.model_id

    def prompt(self, context: C, items: list[I]) -> str:
        raise NotImplementedError

    def template(self, item: I) -> str:
        raise NotImplementedError

    def allowed(self, items: list[I]) -> set[str]:
        raise NotImplementedError

    def explain(
        self, context: C, items: list[I], ctx: RunContext, lookups: object | None = None
    ) -> Explanation:
        if not items:
            return Explanation([], Usage())
        reply = call(
            self.model,
            ctx,
            system=self.system_prompt,
            messages=[{"role": "user", "content": self.prompt(context, items)}],
        )
        if reply.refused:
            return Explanation(
                [Rationale(self.template(item) + DECLINED, Derivation.TEMPLATE) for item in items],
                reply.usage,
                reply.calls,
            )
        return Explanation(self._parse(reply.text, items), reply.usage, reply.calls)

    def _parse(self, text: str, items: list[I]) -> list[Rationale]:
        numbered: dict[int, str] = {}
        for line in text.splitlines():
            m = _NUMBERED.match(line)
            if m:
                numbered[int(m.group(1))] = m.group(2)
        allowed = self.allowed(items)
        out: list[Rationale] = []
        for n, item in enumerate(items, start=1):
            candidate = numbered.get(n)
            if not candidate or names_other_identifier(candidate, allowed, self.pattern):
                # Missing line, or the model named an identifier it was not given: fall back.
                out.append(Rationale(self.template(item) + UNGROUNDED, Derivation.TEMPLATE))
            else:
                out.append(Rationale(candidate, Derivation.MODEL))
        return out

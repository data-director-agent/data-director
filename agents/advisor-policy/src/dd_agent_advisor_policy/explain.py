"""Explainers: turn already-assessed policies into rationale (Blueprint P8, C14).

An explainer receives policy records that were retrieved, matched and assessed before it is
called, and returns one rationale per policy. It cannot add, remove or reorder policies, nor
change an obligation. If a model's rationale names a FAIRsharing identifier it was not given,
the template rationale is used instead and the substitution is noted in the text.

`TemplateExplainer` is the default and needs no credentials. `AnthropicExplainer` is selected
with `DD_POLICY_EXPLAINER=anthropic` and is the only importer of the `anthropic` SDK
(ADR-0006). It is sent registry text and the context, never research data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from dd_agent_advisor_policy.classes import Actor, Obligation, PolicyContext, Strength
from dd_agent_advisor_policy.records import PolicyRecord
from dd_sdk.agent import RunContext
from dd_sdk.contract.models import Derivation
from dd_sdk.tracing import chat_span, record_tokens

if TYPE_CHECKING:
    import anthropic


@dataclass(frozen=True)
class Item:
    """What an explainer is told about one matched policy."""

    record: PolicyRecord
    actor: Actor
    obligations: tuple[Obligation, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Rationale:
    text: str
    derivation: Derivation


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class Explanation:
    """One rationale per item, and the tokens spent. Returned rather than kept on the explainer,
    because one explainer serves concurrent runs."""

    rationales: list[Rationale]
    usage: Usage


class Explainer(Protocol):
    model_id: str | None

    def explain(
        self, context: PolicyContext, items: list[Item], ctx: RunContext
    ) -> Explanation: ...


_IDENTIFIER = re.compile(r"\bFAIRsharing\.[0-9A-Za-z-]+", re.IGNORECASE)


def _kinds(item: Item, strength: Strength) -> str:
    return ", ".join(
        o.kind.value.replace("_", " ") for o in item.obligations if o.strength == strength
    )


def template_rationale(item: Item) -> str:
    r = item.record
    kind = (r.policy_type or "policy").replace("_", " ")
    parts = [
        f"{r.name} ({r.fairsharing_id}) is the {kind} policy FAIRsharing holds for "
        f"{item.actor.name}."
    ]
    for strength, verb in ((Strength.REQUIRED, "requires"), (Strength.RECOMMENDED, "recommends")):
        kinds = _kinds(item, strength)
        if kinds:
            parts.append(f"The record says it {verb}: {kinds}.")
    unstated = _kinds(item, Strength.UNSTATED)
    if unstated:
        parts.append(f"It does not state: {unstated}.")
    parts.append(
        "These are read from FAIRsharing's curated record, not from the policy's own text; "
        "check the policy before relying on them."
    )
    return " ".join(parts)


class TemplateExplainer:
    model_id: str | None = None

    def explain(self, context: PolicyContext, items: list[Item], ctx: RunContext) -> Explanation:
        return Explanation(
            [Rationale(template_rationale(item), Derivation.TEMPLATE) for item in items], Usage()
        )


DEFAULT_MODEL = "claude-sonnet-5-5"

# What the model is told it may and may not do; the prose is a Markdown file beside this module.
SYSTEM_PROMPT = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8").strip()


class AnthropicExplainer:
    """Explains with Claude. Emits one `chat` span carrying model id and token counts."""

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        model_id: str = DEFAULT_MODEL,
        api_key: str | None = None,
    ) -> None:
        """Give a `client` (tests) or an `api_key` (`dd_sdk.credentials.api_key`). The key is
        always passed explicitly, so the SDK's own credential chain is never used (ADR-0026)."""
        if client is None:
            if not api_key:
                raise ValueError("AnthropicExplainer needs a client or an api_key")
            import anthropic as _anthropic

            client = _anthropic.Anthropic(api_key=api_key)
        self._client = client
        self.model_id: str | None = model_id

    def _prompt(self, context: PolicyContext, items: list[Item]) -> str:
        lines = [
            "Context:",
            f"  disciplines: {', '.join(context.disciplines) or '(none)'}",
            f"  kinds of data: {', '.join(context.data_kinds) or '(none)'}",
            f"  publication date: {context.publication_date or '(not given)'}",
            "",
            "Policies:",
        ]
        for n, item in enumerate(items, start=1):
            r = item.record
            stated = "; ".join(
                f"{o.kind.value}: {o.strength.value}"
                + (f" (recorded as {o.recorded_as})" if o.recorded_as else "")
                for o in item.obligations
            )
            clauses = " ".join(
                f"[{name}] {clause.notes}" for name, clause in r.clauses.items() if clause.notes
            )
            lines.append(
                f"{n}. {r.name} [{r.fairsharing_id}] — {item.actor.role.value} "
                f"{item.actor.name!r}; type: {r.policy_type}; obligations: {stated}; "
                f"notes: {' '.join(item.notes) or '(none)'}; "
                f"curators' notes: {clauses[:1500] or '(none)'}"
            )
        return "\n".join(lines)

    def explain(self, context: PolicyContext, items: list[Item], ctx: RunContext) -> Explanation:
        if not items:
            return Explanation([], Usage())
        assert self.model_id is not None
        with chat_span(ctx.tracer, self.model_id) as span:
            response = self._client.messages.create(
                model=self.model_id,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": self._prompt(context, items)}],
            )
            usage = Usage(response.usage.input_tokens, response.usage.output_tokens)
            record_tokens(span, usage.input_tokens, usage.output_tokens)
        if response.stop_reason == "refusal":
            return Explanation(
                [
                    Rationale(
                        template_rationale(item) + " (Model declined; template used.)",
                        Derivation.TEMPLATE,
                    )
                    for item in items
                ],
                usage,
            )
        text = "".join(block.text for block in response.content if block.type == "text")
        return Explanation(self._parse(text, items), usage)

    def _parse(self, text: str, items: list[Item]) -> list[Rationale]:
        numbered: dict[int, str] = {}
        for line in text.splitlines():
            m = re.match(r"\s*(\d+)[.)]\s+(.*\S)", line)
            if m:
                numbered[int(m.group(1))] = m.group(2)
        allowed = {item.record.fairsharing_id.lower() for item in items}
        out: list[Rationale] = []
        for n, item in enumerate(items, start=1):
            candidate = numbered.get(n)
            mentioned = {x.lower() for x in _IDENTIFIER.findall(candidate or "")}
            if not candidate or (mentioned - allowed):
                # Missing line, or the model named an identifier it was not given: fall back.
                out.append(
                    Rationale(
                        template_rationale(item)
                        + " (Model rationale replaced: ungrounded reference.)",
                        Derivation.TEMPLATE,
                    )
                )
            else:
                out.append(Rationale(candidate, Derivation.MODEL))
        return out

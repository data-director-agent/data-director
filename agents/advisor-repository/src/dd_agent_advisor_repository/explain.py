"""Explainers: turn already-decided candidates into rationale (Blueprint P8, C14).

An explainer receives repositories that were retrieved, assessed and ranked before it is called,
and returns one rationale per candidate. It cannot add, remove or reorder candidates, nor change
a judgement. If a model's rationale names a re3data or FAIRsharing identifier it was not given,
the template rationale is used instead and the substitution is noted in the text.

`TemplateExplainer` is the default and needs no credentials. `ModelExplainer` is selected
with `DD_REPOSITORY_EXPLAINER=model` and calls whichever model the agent's settings name, through
the SDK's model seam (`dd_sdk.model`, `dd_sdk.model_provider`).
It is sent registry text and the needs, never research data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from dd_agent_advisor_repository.assess import Assessment
from dd_agent_advisor_repository.classes import CandidateBasis, RepositoryNeeds
from dd_agent_advisor_repository.records import DatabaseRecord, Re3dataRecord
from dd_sdk.agent import RunContext
from dd_sdk.contract.models import Derivation
from dd_sdk.model import Model, call
from dd_sdk.model import Usage as Usage
from dd_sdk.prompts import ModelCallLog


@dataclass(frozen=True)
class Item:
    """What an explainer is told about one candidate."""

    record: Re3dataRecord
    database: DatabaseRecord | None
    basis: CandidateBasis
    assessment: Assessment
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Rationale:
    text: str
    derivation: Derivation


@dataclass(frozen=True)
class Explanation:
    """One rationale per item, and the tokens spent. Returned rather than kept on the explainer,
    because one explainer serves concurrent runs."""

    rationales: list[Rationale]
    usage: Usage
    # The model calls made and the prompts sent (dd_sdk.prompts); None if no model was called.
    calls: ModelCallLog | None = None


class Explainer(Protocol):
    model_id: str | None

    def explain(
        self, needs: RepositoryNeeds, items: list[Item], ctx: RunContext
    ) -> Explanation: ...


_IDENTIFIER = re.compile(r"\b(r3d\d+|FAIRsharing\.[0-9A-Za-z-]+)", re.IGNORECASE)


def template_rationale(item: Item) -> str:
    r = item.record
    if item.basis == CandidateBasis.MANDATED:
        lead = f"{r.name} ({r.re3data_id}) was named as mandated, so it is described, not ranked."
    else:
        why = f" {' '.join(item.reasons)}" if item.reasons else ""
        lead = f"{r.name} ({r.re3data_id}) is shortlisted.{why}"
    kind = f" re3data lists it as {', '.join(r.types)}." if r.types else ""
    subjects = f" Subjects: {'; '.join(r.subject_names()[:3])}." if r.subjects else ""
    gaps = (
        f" Not met or not stated: {' '.join(item.assessment.misses)}"
        if item.assessment.misses
        else ""
    )
    return (
        f"{lead}{kind}{subjects}{gaps} The researcher chooses; "
        "the repositories were found by registry search and ranking, not by a model."
    )


class TemplateExplainer:
    model_id: str | None = None

    def explain(self, needs: RepositoryNeeds, items: list[Item], ctx: RunContext) -> Explanation:
        return Explanation(
            [Rationale(template_rationale(item), Derivation.TEMPLATE) for item in items], Usage()
        )


DEFAULT_MODEL = "claude-sonnet-5-5"

# What the model is told it may and may not do; the prose is a Markdown file beside this module.
SYSTEM_PROMPT = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8").strip()


class ModelExplainer:
    """Explains with the model the agent's settings name (`dd_sdk.model_provider`). The call goes
    through `dd_sdk.model.call`, which records its `chat` span, its tokens and its prompt."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self.model_id: str | None = model.model_id

    def _prompt(self, needs: RepositoryNeeds, items: list[Item]) -> str:
        lines = [
            "Needs:",
            f"  themes: {', '.join(needs.themes) or '(none)'}",
            f"  kinds of data: {', '.join(needs.data_kinds) or '(none)'}",
            f"  access: {needs.access or '(not decided)'}",
            f"  affiliation: {needs.affiliation.name if needs.affiliation else '(none)'}",
            "",
            "Repositories:",
        ]
        for n, item in enumerate(items, start=1):
            r, a = item.record, item.assessment
            desc = (r.description or "").strip().replace("\n", " ")
            lines.append(
                f"{n}. {r.name} [{r.re3data_id}] — basis: {item.basis.value}; "
                f"types: {', '.join(r.types)}; subjects: {'; '.join(r.subject_names()[:6])}; "
                f"meets: {' '.join(a.meets) or '(none)'}; "
                f"misses: {' '.join(a.misses) or '(none)'}; "
                f"notes: {' '.join(a.notes) or '(none)'}; "
                f"registry description: {desc[:600]}"
            )
        return "\n".join(lines)

    def explain(self, needs: RepositoryNeeds, items: list[Item], ctx: RunContext) -> Explanation:
        if not items:
            return Explanation([], Usage())
        reply = call(
            self.model,
            ctx,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self._prompt(needs, items)}],
        )
        if reply.refused:
            return Explanation(
                [
                    Rationale(
                        template_rationale(item) + " (Model declined; template used.)",
                        Derivation.TEMPLATE,
                    )
                    for item in items
                ],
                reply.usage,
                reply.calls,
            )
        return Explanation(self._parse(reply.text, items), reply.usage, reply.calls)

    def _parse(self, text: str, items: list[Item]) -> list[Rationale]:
        numbered: dict[int, str] = {}
        for line in text.splitlines():
            m = re.match(r"\s*(\d+)[.)]\s+(.*\S)", line)
            if m:
                numbered[int(m.group(1))] = m.group(2)
        allowed = set()
        for item in items:
            allowed.add(item.record.re3data_id.lower())
            if item.record.fairsharing_id:
                allowed.add(item.record.fairsharing_id.lower())
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

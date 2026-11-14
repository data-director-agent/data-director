"""Explainers: turn already-decided recommendations into rationale (C14).

The grounding invariant lives here as a shape: an explainer receives records that were
retrieved and ranked before it is called, and returns one rationale per recommendation. It
cannot add, remove or reorder recommendations. If a model's rationale names a FAIRsharing
identifier that was not retrieved, the template rationale is used instead and the substitution
is noted in the text.

`TemplateExplainer` is the default and needs no credentials. `ModelExplainer` is selected
with `DD_STANDARDS_EXPLAINER=model` and calls whichever model the agent's settings name, through
the SDK's model seam (`dd_sdk.model`, `dd_sdk.model_provider`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from dd_agent_advisor_standards.classes import DatasetProfile, RecommendationKind
from dd_agent_advisor_standards.fairsharing.records import Record
from dd_sdk.agent import RunContext
from dd_sdk.contract.models import Derivation
from dd_sdk.model import Model, call
from dd_sdk.model import Usage as Usage
from dd_sdk.prompts import ModelCallLog

# (record, kind, target, ranking reasons) — what an explainer is told about each recommendation.
Item = tuple[Record, RecommendationKind, str, tuple[str, ...]]

_FAIRSHARING_ID = re.compile(r"FAIRsharing\.[0-9a-z-]+", re.IGNORECASE)


@dataclass(frozen=True)
class Rationale:
    text: str
    derivation: Derivation


@dataclass(frozen=True)
class Explanation:
    """One rationale per item, and the tokens spent on this call.

    Usage is returned rather than kept on the explainer, because one explainer instance serves
    concurrent runs (`dd_sdk.serve` runs each request on its own thread).
    """

    rationales: list[Rationale]
    usage: Usage
    # The model calls made and the prompts sent (dd_sdk.prompts); None if no model was called.
    calls: ModelCallLog | None = None


class Explainer(Protocol):
    model_id: str | None

    def explain(
        self, profile: DatasetProfile, items: list[Item], ctx: RunContext
    ) -> Explanation: ...


_KIND_PHRASE = {
    RecommendationKind.CONTROLLED_VOCABULARY: (
        "a controlled vocabulary for linking field values to shared concepts"
    ),
    RecommendationKind.ONTOLOGY: (
        "an ontology for aligning the dataset's structure with a shared model"
    ),
    RecommendationKind.TERMINOLOGY_UNCLASSIFIED: (
        "a terminology resource (the registry record does not say whether it is a "
        "vocabulary or an ontology)"
    ),
    RecommendationKind.DATA_FORMAT: "an open data format for the dataset",
    RecommendationKind.FIELD_FORMAT: "a field-level format standard",
}


def template_rationale(
    record: Record, kind: RecommendationKind, target: str, reasons: tuple[str, ...]
) -> str:
    what = _KIND_PHRASE[kind]
    where = (
        f"for the field {target.removeprefix('field:')!r}"
        if target.startswith("field:")
        else "for the dataset"
    )
    status = f" Its FAIRsharing status is {record.status!r}." if record.status else ""
    subjects = f" Registered subjects: {', '.join(record.subjects[:4])}." if record.subjects else ""
    return (
        f"{record.name} ({record.fairsharing_id}) is recommended as {what} {where}."
        f"{status}{subjects} Ranking signals: {', '.join(reasons)}. "
        "Identity was decided by retrieval and ranking, not by a model."
    )


class TemplateExplainer:
    model_id: str | None = None

    def explain(self, profile: DatasetProfile, items: list[Item], ctx: RunContext) -> Explanation:
        return Explanation(
            [Rationale(template_rationale(*item), Derivation.TEMPLATE) for item in items], Usage()
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

    def _prompt(self, profile: DatasetProfile, items: list[Item]) -> str:
        lines = [
            "Dataset profile:",
            f"  title: {profile.title or '(none)'}",
            f"  description: {profile.description or '(none)'}",
            f"  keywords: {', '.join(profile.keywords) or '(none)'}",
            f"  themes: {', '.join(profile.themes) or '(none)'}",
            "  fields: "
            + (
                ", ".join(f"{f.name} ({f.field_type or 'unknown'})" for f in profile.fields)
                or "(none)"
            ),
            "",
            "Selected standards:",
        ]
        for n, (record, kind, target, reasons) in enumerate(items, start=1):
            desc = (record.description or "").strip().replace("\n", " ")
            lines.append(
                f"{n}. {record.name} [{record.fairsharing_id}] — kind: {kind.value}; "
                f"target: {target}; "
                f"status: {record.status}; subjects: {', '.join(record.subjects[:6])}; "
                f"registry description: {desc[:600]}; ranking signals: {', '.join(reasons)}"
            )
        return "\n".join(lines)

    def explain(self, profile: DatasetProfile, items: list[Item], ctx: RunContext) -> Explanation:
        if not items:
            return Explanation([], Usage())
        reply = call(
            self.model,
            ctx,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self._prompt(profile, items)}],
        )
        if reply.refused:
            return Explanation(
                [
                    Rationale(
                        template_rationale(*item) + " (Model declined; template used.)",
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
        allowed = {r.fairsharing_id.lower() for r, *_ in items}
        out: list[Rationale] = []
        for n, item in enumerate(items, start=1):
            candidate = numbered.get(n)
            mentioned = {x.lower() for x in _FAIRSHARING_ID.findall(candidate or "")}
            if not candidate or (mentioned - allowed):
                # Missing line, or the model named an identifier it was not given: fall back.
                out.append(
                    Rationale(
                        template_rationale(*item)
                        + " (Model rationale replaced: ungrounded reference.)",
                        Derivation.TEMPLATE,
                    )
                )
            else:
                out.append(Rationale(candidate, Derivation.MODEL))
        return out

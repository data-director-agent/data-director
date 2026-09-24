"""Explainers: turn already-decided recommendations into rationale (C14).

The grounding invariant lives here as a shape: an explainer receives records that were
retrieved and ranked before it is called, and returns one rationale per recommendation. It
cannot add, remove or reorder recommendations. If a model's rationale names a FAIRsharing
identifier that was not retrieved, the template rationale is used instead and the substitution
is noted in the text.

`TemplateExplainer` is the default and needs no credentials. `AnthropicExplainer` is selected
with `DD_R3_EXPLAINER=anthropic` and is the only importer of the `anthropic` SDK (ADR-0006).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from dd_agent_r3.fairsharing.records import Record
from dd_sdk.agent import RunContext
from dd_sdk.contract.models import DatasetProfile, Derivation, RecommendationKind
from dd_sdk.tracing import chat_span, record_tokens

if TYPE_CHECKING:
    import anthropic

# (record, kind, target, ranking reasons) — what an explainer is told about each recommendation.
Item = tuple[Record, RecommendationKind, str, tuple[str, ...]]

_FAIRSHARING_ID = re.compile(r"FAIRsharing\.[0-9a-z-]+", re.IGNORECASE)


@dataclass(frozen=True)
class Rationale:
    text: str
    derivation: Derivation


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


class Explainer(Protocol):
    model_id: str | None
    usage: Usage

    def explain(
        self, profile: DatasetProfile, items: list[Item], ctx: RunContext
    ) -> list[Rationale]: ...


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

    def __init__(self) -> None:
        self.usage = Usage()

    def explain(
        self, profile: DatasetProfile, items: list[Item], ctx: RunContext
    ) -> list[Rationale]:
        return [Rationale(template_rationale(*item), Derivation.TEMPLATE) for item in items]


DEFAULT_MODEL = "claude-opus-5"

SYSTEM_PROMPT = (
    "You write short explanations for a research data steward. You are given a dataset profile "
    "(metadata only, never data values) and a numbered list of standards that have ALREADY been "
    "selected from the FAIRsharing registry by a deterministic ranking step. For each numbered "
    "item, "
    "write one or two sentences explaining why that standard fits this dataset, using only the "
    "registry description supplied. Do not recommend anything not in the list, do not rank or "
    "reorder, and do not mention identifiers other than the one given for each item. "
    "Reply with exactly one line per item, in order, formatted `N. <explanation>`."
)


class AnthropicExplainer:
    """Explains with Claude. Emits one `chat` span carrying model id and token counts."""

    def __init__(
        self, client: anthropic.Anthropic | None = None, model_id: str = DEFAULT_MODEL
    ) -> None:
        import anthropic as _anthropic

        self._client = client or _anthropic.Anthropic()
        self.model_id: str | None = model_id
        self.usage = Usage()

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

    def explain(
        self, profile: DatasetProfile, items: list[Item], ctx: RunContext
    ) -> list[Rationale]:
        if not items:
            return []
        assert self.model_id is not None
        with chat_span(ctx.tracer, self.model_id) as span:
            response = self._client.messages.create(
                model=self.model_id,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": self._prompt(profile, items)}],
            )
            self.usage = Usage(response.usage.input_tokens, response.usage.output_tokens)
            record_tokens(span, self.usage.input_tokens, self.usage.output_tokens)
        if response.stop_reason == "refusal":
            return [
                Rationale(
                    template_rationale(*item) + " (Model declined; template used.)",
                    Derivation.TEMPLATE,
                )
                for item in items
            ]
        text = "".join(block.text for block in response.content if block.type == "text")
        return self._parse(text, items)

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

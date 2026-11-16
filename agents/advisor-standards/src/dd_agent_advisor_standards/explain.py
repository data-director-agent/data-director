"""Explainers: say why each recommendation the rules chose fits (C14), and what an explainer
may add beside them.

The grounding invariant lives here as a shape: an explainer receives records that were retrieved
and ranked before it is called, and returns one rationale per rule pick, in order. It cannot
remove or reorder a rule pick. A model explainer (`advise.ModelAdvisor`) may also add
recommendations, each naming a record retrieved in this run, and note a concern beside a rule
pick; the agent checks neither less than the rules' own picks.

`TemplateExplainer` needs no credentials and is selected with `DD_STANDARDS_EXPLAINER=template`.
`advise.ModelAdvisor` is the default.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from dd_agent_advisor_standards.classes import DatasetProfile, RecommendationKind
from dd_agent_advisor_standards.fairsharing.records import Record
from dd_agent_advisor_standards.retrieve import RetrievalAdapter
from dd_sdk.agent import RunContext
from dd_sdk.contract.models import Derivation
from dd_sdk.model import Usage as Usage
from dd_sdk.prompts import ModelCallLog

# (record, kind, target, ranking reasons) — what an explainer is told about each recommendation.
Item = tuple[Record, RecommendationKind, str, tuple[str, ...]]

_FAIRSHARING_ID = re.compile(r"FAIRsharing\.[0-9a-z-]+", re.IGNORECASE)


def names_other_identifier(text: str, allowed: set[str]) -> bool:
    """Whether `text` names a FAIRsharing identifier outside `allowed`."""
    wanted = {a.lower() for a in allowed}
    return any(m.lower() not in wanted for m in _FAIRSHARING_ID.findall(text))


@dataclass(frozen=True)
class Rationale:
    text: str
    derivation: Derivation


@dataclass(frozen=True)
class Addition:
    """A recommendation a model added: a record retrieved in this run, the kind and target it
    chose, and its rationale. The agent has already checked it (`advise._apply`)."""

    record: Record
    kind: RecommendationKind
    target: str
    rationale: Rationale


@dataclass(frozen=True)
class Explanation:
    """One rationale per item, and the tokens spent on this call; with a model, what it added,
    the concern it noted beside each item (or None), and what the agent did not take from it.

    Usage is returned rather than kept on the explainer, because one explainer instance serves
    concurrent runs (`dd_sdk.serve` runs each request on its own thread).
    """

    rationales: list[Rationale]
    usage: Usage
    # The model calls made and the prompts sent (dd_sdk.prompts); None if no model was called.
    calls: ModelCallLog | None = None
    concerns: Sequence[str | None] = ()
    additions: Sequence[Addition] = ()
    remarks: Sequence[str] = field(default_factory=list)


@dataclass
class Lookups:
    """What a model explainer may search in one run, and every record retrieved so far, by
    FAIRsharing id. The agent builds it for each run; a record a search retrieves is added here,
    with its `retrieval` span, before it may be cited."""

    retrieval: RetrievalAdapter | None = None
    records: dict[str, Record] = field(default_factory=dict)


class Explainer(Protocol):
    model_id: str | None

    def explain(
        self,
        profile: DatasetProfile,
        items: list[Item],
        ctx: RunContext,
        lookups: Lookups | None = None,
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

    def explain(
        self,
        profile: DatasetProfile,
        items: list[Item],
        ctx: RunContext,
        lookups: Lookups | None = None,
    ) -> Explanation:
        return Explanation(
            [Rationale(template_rationale(*item), Derivation.TEMPLATE) for item in items], Usage()
        )

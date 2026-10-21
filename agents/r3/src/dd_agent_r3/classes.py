"""The input and payload classes of r3.standards-advisor, as Pydantic models (ADR-0019).

`schema/r3.yaml` is the source; `ClassSchema.of` compares each model with the schema generated
from it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Derivation, Frozen, Grounded


class RecommendationKind(StrEnum):
    CONTROLLED_VOCABULARY = "controlled_vocabulary"
    ONTOLOGY = "ontology"
    TERMINOLOGY_UNCLASSIFIED = "terminology_unclassified"
    DATA_FORMAT = "data_format"
    FIELD_FORMAT = "field_format"


class TableField(Frozen):
    name: str
    field_type: str | None = None
    field_format: str | None = None
    field_description: str | None = None


class DatasetProfile(Frozen):
    schema_class: Literal["DatasetProfile"] = "DatasetProfile"
    title: str | None = None
    description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    media_types: list[str] = Field(default_factory=list)
    fields: list[TableField] = Field(default_factory=list)


class Recommendation(Grounded):
    """Names its resource only in `grounded_on`; the description is in evidence (ADR-0015)."""

    kind: RecommendationKind
    target: str
    score: float | None = None
    rationale: str
    rationale_derivation: Derivation
    classification_derivation: Derivation | None = None


class SearchedSummary(Frozen):
    queries: list[str] = Field(default_factory=list)
    snapshot_ref: str | None = None
    candidates_retrieved: int | None = None
    candidates_qualifying: int | None = None


class Recommendations(Grounded):
    schema_class: Literal["Recommendations"] = "Recommendations"
    items: list[Recommendation] = Field(default_factory=list)
    searched: SearchedSummary | None = None

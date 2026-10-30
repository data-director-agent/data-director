"""The input and payload classes of advisor.metadata, as Pydantic models (ADR-0019).

`schema/metadata.yaml` is the source; `ClassSchema.of` compares each model with the schema
generated from it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Frozen, Grounded


class MetadataDraftRequest(Frozen):
    schema_class: Literal["MetadataDraftRequest"] = "MetadataDraftRequest"
    title: str | None = None
    description: str | None = None
    creators: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    publication_year: int | None = None
    target_standard: str | None = None


class DraftField(Frozen):
    name: str
    value: str | None = None
    status: str


class MetadataDraft(Grounded):
    schema_class: Literal["MetadataDraft"] = "MetadataDraft"
    standard: str
    standard_reason: str
    fields: list[DraftField] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

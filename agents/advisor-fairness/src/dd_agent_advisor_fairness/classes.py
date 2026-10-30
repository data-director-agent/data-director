"""The input and payload classes of advisor.fairness, as Pydantic models (ADR-0019).

`schema/fairness.yaml` is the source; `ClassSchema.of` compares each model with the schema
generated from it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Frozen, Grounded


class PublishedRecord(Frozen):
    schema_class: Literal["PublishedRecord"] = "PublishedRecord"
    identifier: str | None = None
    title: str | None = None
    licence: str | None = None
    keywords: list[str] = Field(default_factory=list)
    creators: list[str] = Field(default_factory=list)
    creator_identifiers: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    related_identifiers: list[str] = Field(default_factory=list)
    access_protocol: str | None = None


class FairCheck(Frozen):
    principle: str
    check: str
    met: bool
    recommendation: str | None = None


class FairnessReport(Grounded):
    schema_class: Literal["FairnessReport"] = "FairnessReport"
    checks: list[FairCheck] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

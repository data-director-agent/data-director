"""The input and payload classes of advisor.fairness, as Pydantic models (docs/specs/contract.md).

`schema/fairness.yaml` is the source; `ClassSchema.of` compares each model with the schema
generated from it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import (
    ApprovedMetadataRecord,
    CurrentVersion,
    Derivation,
    DocumentVersionRef,
    Frozen,
    Grounded,
)


class FairPrinciple(StrEnum):
    F = "F"
    A = "A"
    I = "I"  # noqa: E741 - the principle's letter
    R = "R"


class PublishedRecord(Frozen):
    schema_class: Literal["PublishedRecord"] = "PublishedRecord"
    identifier: str | None = None
    title: str | None = None
    description: str | None = None
    licence: str | None = None
    keywords: list[str] = Field(default_factory=list)
    creators: list[str] = Field(default_factory=list)
    creator_identifiers: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    related_identifiers: list[str] = Field(default_factory=list)
    access_protocol: str | None = None


class ProjectMetadataDraft(Frozen):
    schema_class: Literal["ProjectMetadataDraft"] = "ProjectMetadataDraft"
    draft_text: str | None = None
    # Filled by the conductor in a project (`GivenProjectMetadataRecord`).
    project_metadata_draft: CurrentVersion | None = None
    project_metadata_approved: ApprovedMetadataRecord | None = None


class FairCheck(Frozen):
    principle: str
    check: str
    met: bool
    after_deposit: bool | None = None
    newly_met: bool | None = None
    recommendation: str | None = None
    recommendation_derivation: Derivation | None = None


class PrincipleTally(Frozen):
    principle_group: FairPrinciple
    tally_met: int
    tally_assessed: int


class FairnessReport(Grounded):
    schema_class: Literal["FairnessReport"] = "FairnessReport"
    checks: list[FairCheck] = Field(default_factory=list)
    principle_tallies: list[PrincipleTally] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    assessed_version: DocumentVersionRef | None = None
    compared_with: DocumentVersionRef | None = None
    limitations: list[str] = Field(default_factory=list)

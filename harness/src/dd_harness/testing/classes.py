"""The doubles' own classes, declared in `../schema/doubles.yaml`.

The doubles read and return these `Probe*` classes. The conductor knows them only from the doubles'
cards, as it knows every real agent's classes (docs/specs/contract.md). After an edit to the schema,
keep these models in step; `ClassSchema.of` refuses a model that has drifted.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import (
    ApprovedMetadataRecord,
    ChosenRepository,
    CurrentVersion,
    Derivation,
    DocumentKind,
    Frozen,
    Grounded,
    ProjectDocument,
    ProjectFact,
)


class ProbeRecord(Frozen):
    schema_class: Literal["ProbeRecord"] = "ProbeRecord"
    identifier: str | None = None
    title: str | None = None
    licence: str | None = None
    creators: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class ProbeClaim(Frozen):
    schema_class: Literal["ProbeClaim"] = "ProbeClaim"
    text: str


class ProbeProfile(Frozen):
    schema_class: Literal["ProbeProfile"] = "ProbeProfile"
    title: str | None = None


class ProbeDocumentRequest(Frozen):
    schema_class: Literal["ProbeDocumentRequest"] = "ProbeDocumentRequest"
    document_kind: DocumentKind


class ProbeReading(Frozen):
    schema_class: Literal["ProbeReading"] = "ProbeReading"
    title: str | None = None
    project_documents: list[ProjectDocument] = Field(default_factory=list)
    project_decisions: list[ProjectFact] = Field(default_factory=list)
    project_repository: ChosenRepository | None = None
    project_metadata_draft: CurrentVersion | None = None
    project_metadata_approved: ApprovedMetadataRecord | None = None


class ProbeReview(Grounded):
    schema_class: Literal["ProbeReview"] = "ProbeReview"
    score: float | None = None


class ProbeCheck(Grounded):
    schema_class: Literal["ProbeCheck"] = "ProbeCheck"
    rationale: str
    rationale_derivation: Derivation


class ProbeFindings(Grounded):
    schema_class: Literal["ProbeFindings"] = "ProbeFindings"
    proposed_facts: list[ProjectFact] = Field(default_factory=list)

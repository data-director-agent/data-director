"""The input and payload classes of quality.reviewer, as Pydantic models (ADR-0019).

`schema/quality.yaml` is the source; `ClassSchema.of` compares each model with the schema
generated from it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Derivation, Frozen, Grounded


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class MetadataRecord(Frozen):
    schema_class: Literal["MetadataRecord"] = "MetadataRecord"
    identifier: str | None = None
    title: str | None = None
    description: str | None = None
    licence: str | None = None
    creators: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class Finding(Grounded):
    criterion: str
    severity: Severity
    message: str
    derivation: Derivation


class QualityReview(Grounded):
    schema_class: Literal["QualityReview"] = "QualityReview"
    score: float | None = None
    findings: list[Finding] = Field(default_factory=list)

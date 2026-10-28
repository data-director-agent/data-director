"""The doubles' own classes, declared in `../schema/doubles.yaml`.

The doubles read and return these `Probe*` classes. The conductor knows them only from the
doubles' cards, as it knows every real agent's classes (ADR-0019). After an edit to the schema,
keep these models in step; `ClassSchema.of` refuses a model that has drifted.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Derivation, Frozen, Grounded


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


class ProbeReview(Grounded):
    schema_class: Literal["ProbeReview"] = "ProbeReview"
    score: float | None = None


class ProbeCheck(Grounded):
    schema_class: Literal["ProbeCheck"] = "ProbeCheck"
    rationale: str
    rationale_derivation: Derivation

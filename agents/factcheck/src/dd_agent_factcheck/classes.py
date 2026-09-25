"""The input and payload classes of fact.checker, as Pydantic models (ADR-0019).

`schema/factcheck.yaml` is the source; `ClassSchema.of` compares each model with the schema
generated from it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from dd_sdk.contract.models import Derivation, Frozen, Grounded


class Verdict(StrEnum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    UNVERIFIABLE = "unverifiable"


class Claim(Frozen):
    schema_class: Literal["Claim"] = "Claim"
    text: str
    subject_uri: str | None = None
    context: str | None = None


class FactCheck(Grounded):
    schema_class: Literal["FactCheck"] = "FactCheck"
    verdict: Verdict
    rationale: str
    rationale_derivation: Derivation

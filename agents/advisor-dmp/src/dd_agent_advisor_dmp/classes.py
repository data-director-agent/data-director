"""The input and payload classes of advisor.dmp, as Pydantic models (ADR-0019).

`schema/dmp.yaml` is the source; `ClassSchema.of` compares each model with the schema generated
from it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Frozen, Grounded


class SharingCommitment(Frozen):
    output: str
    repository: str | None = None
    access: str | None = None
    licence: str | None = None


class DmpCommitments(Frozen):
    schema_class: Literal["DmpCommitments"] = "DmpCommitments"
    dmp_identifier: str | None = None
    committed_outputs: list[SharingCommitment] = Field(default_factory=list)
    planned_outputs: list[SharingCommitment] = Field(default_factory=list)


class Discrepancy(Frozen):
    output: str
    aspect: str
    committed: str | None = None
    planned: str | None = None
    message: str


class DmpDiscrepancies(Grounded):
    schema_class: Literal["DmpDiscrepancies"] = "DmpDiscrepancies"
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

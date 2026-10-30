"""The input and payload classes of advisor.ethics, as Pydantic models (ADR-0019).

`schema/ethics.yaml` is the source; `ClassSchema.of` compares each model with the schema generated
from it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Frozen, Grounded


class SensitivityContext(Frozen):
    schema_class: Literal["SensitivityContext"] = "SensitivityContext"
    title: str | None = None
    description: str | None = None
    fields: list[str] = Field(default_factory=list)
    involves_people: bool | None = None
    embargo_intended: bool | None = None


class SensitivityFlag(Frozen):
    field: str
    category: str
    matched: str


class SensitivityFlags(Grounded):
    schema_class: Literal["SensitivityFlags"] = "SensitivityFlags"
    flags: list[SensitivityFlag] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

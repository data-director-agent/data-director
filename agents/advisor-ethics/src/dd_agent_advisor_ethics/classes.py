"""The input and payload classes of advisor.ethics, as Pydantic models (docs/specs/contract.md).

`schema/ethics.yaml` is the source; `ClassSchema.of` compares each model with the schema generated
from it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from dd_sdk.contract.inventory import FileInventory, PersonalDataFinding
from dd_sdk.contract.models import Derivation, Frozen, Grounded


class SensitivityContext(Frozen):
    schema_class: Literal["SensitivityContext"] = "SensitivityContext"
    title: str | None = None
    description: str | None = None
    fields: list[str] = Field(default_factory=list)
    involves_people: bool | None = None
    embargo_intended: bool | None = None
    # Filled by the conductor in a project (`GivenProjectInventory`).
    project_file_inventory: FileInventory | None = None


class SensitivityFlag(Frozen):
    field: str
    category: str
    files: list[str] = Field(default_factory=list)
    matched: str | None = None
    reason: str | None = None
    derivation: Derivation


class DataUseTerm(Frozen):
    term_id: str = Field(pattern=r"^DUO:[0-9]{7}$")
    shorthand: str | None = None
    term_label: str
    term_kind: Literal["permission", "modifier"]
    term_iri: str


class SensitivityQuestion(Frozen):
    text: str
    derivation: Derivation
    data_use_terms: list[DataUseTerm] = Field(default_factory=list)


class SensitivityFlags(Grounded):
    schema_class: Literal["SensitivityFlags"] = "SensitivityFlags"
    flags: list[SensitivityFlag] = Field(default_factory=list)
    questions: list[SensitivityQuestion] = Field(default_factory=list)
    # Absent and empty differ: absent, no detector ran (docs/specs/personal-data.md).
    inventory_findings: list[PersonalDataFinding] | None = None
    limitations: list[str] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)

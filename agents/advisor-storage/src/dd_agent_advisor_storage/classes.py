"""The input and payload classes of advisor.storage, as Pydantic models (docs/specs/contract.md).

`schema/storage.yaml` is the source; `ClassSchema.of` compares each model with the schema
generated from it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from dd_sdk.contract.facts import InstitutionStorage
from dd_sdk.contract.models import Derivation, Frozen, Grounded


class PersonalDataAnswer(StrEnum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class StorageNeeds(Frozen):
    schema_class: Literal["StorageNeeds"] = "StorageNeeds"
    expected_volume_gb: int | None = Field(default=None, ge=0)
    involves_personal_data: PersonalDataAnswer | None = None
    external_collaborators: bool | None = None
    # Filled by the conductor from the profile (`GivenInstitutionStorage`).
    institution_storage: list[InstitutionStorage] = Field(default_factory=list)


class StorageOption(Grounded):
    storage_id: str
    offers: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)


class ExcludedStorage(Grounded):
    storage_id: str
    excluded_because: str


class StorageAdvice(Grounded):
    schema_class: Literal["StorageAdvice"] = "StorageAdvice"
    storage_options: list[StorageOption] = Field(default_factory=list)
    excluded_storage: list[ExcludedStorage] = Field(default_factory=list)
    plan_questions: list[str] = Field(default_factory=list)
    summary: str | None = None
    summary_derivation: Derivation | None = None
    limitations: list[str] = Field(default_factory=list)

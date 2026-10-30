"""The payload class of advisor.files, as Pydantic models (ADR-0019).

`schema/files.yaml` is the source; `ClassSchema.of` compares each model with the schema generated
from it. The input is the core contract's `FileInventory` (ADR-0034).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Frozen, Grounded


class JudgedBy(StrEnum):
    MEDIA_TYPE = "media_type"
    EXTENSION = "extension"
    NOTHING = "nothing"


class FileAssessment(Frozen):
    path: str
    extension: str
    format_name: str
    media_type: str | None = None
    open_format: bool
    judged_by: JudgedBy


class FormatAssessment(Grounded):
    schema_class: Literal["FormatAssessment"] = "FormatAssessment"
    assessments: list[FileAssessment] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

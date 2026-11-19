"""The payload class of advisor.files, as Pydantic models (docs/specs/contract.md).

`schema/files.yaml` is the source; `ClassSchema.of` compares each model with the schema generated
from it. The input is the core contract's `FileInventory` (docs/specs/projects.md).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Frozen, Grounded


class JudgedBy(StrEnum):
    PRONOM = "pronom"
    PRONOM_UNLISTED = "pronom_unlisted"
    MEDIA_TYPE = "media_type"
    EXTENSION = "extension"
    NOTHING = "nothing"


class CheckKind(StrEnum):
    FREE_TEXT = "free_text"
    COORDINATES = "coordinates"
    THIRD_PARTY = "third_party"
    GOVERNANCE = "governance"
    SYSTEM_FILE = "system_file"
    EMPTY = "empty"
    DUPLICATE = "duplicate"
    EXTENSION_MISMATCH = "extension_mismatch"


class FileCheck(Frozen):
    path: str
    kind: CheckKind
    matched: str | None = None
    question: str
    related_paths: list[str] = Field(default_factory=list)


class FileAssessment(Frozen):
    path: str
    extension: str
    format_name: str
    media_type: str | None = None
    open_format: bool
    judged_by: JudgedBy
    pronom_id: str | None = None


class FormatAssessment(Grounded):
    schema_class: Literal["FormatAssessment"] = "FormatAssessment"
    assessments: list[FileAssessment] = Field(default_factory=list)
    checks: list[FileCheck] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

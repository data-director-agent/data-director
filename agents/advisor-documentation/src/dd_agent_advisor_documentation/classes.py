"""The input and payload classes of advisor.documentation, as Pydantic models (ADR-0019).

`schema/documentation.yaml` is the source; `ClassSchema.of` compares each model with the schema
generated from it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Frozen, Grounded


class DraftStatus(StrEnum):
    DRAFTED = "drafted"
    NEEDS_RESEARCHER = "needs_researcher"


class DocumentationRequest(Frozen):
    schema_class: Literal["DocumentationRequest"] = "DocumentationRequest"
    title: str
    description: str | None = None
    creators: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)


class ReadmeSection(Frozen):
    heading: str
    text: str | None = None
    draft_status: DraftStatus


class DictionaryEntry(Frozen):
    field: str
    definition: str | None = None
    unit: str | None = None
    missing_values: str | None = None
    draft_status: DraftStatus


class DocumentationDraft(Grounded):
    schema_class: Literal["DocumentationDraft"] = "DocumentationDraft"
    readme_sections: list[ReadmeSection] = Field(default_factory=list)
    dictionary: list[DictionaryEntry] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

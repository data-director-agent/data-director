"""The input every drafter accepts, `DraftRequest`, and the project document versions it carries
(docs/specs/projects.md, docs/specs/drafting.md). A core input class, like Message, so that one
drafter can replace another without its caller changing. `models` re-exports each name, so that
it stays within its size limit; the field names are the LinkML schema's.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from dd_sdk.contract.base import UUID7_PATTERN, Frozen
from dd_sdk.contract.facts import (
    DocumentKind,
    InstitutionStorage,
    ProjectDocument,
    ProjectFact,
    ResearcherRecord,
    VersionState,
)
from dd_sdk.contract.inventory import FileInventory
from dd_sdk.contract.questions import DraftAnswer, SharedAnswer
from dd_sdk.contract.requirements import RepositoryRequirements


class DocumentVersionRef(Frozen):
    """One version of a project document, numbered from 1 within it (docs/specs/projects.md)."""

    document_id: str = Field(pattern=UUID7_PATTERN)
    version: int = Field(ge=1)  # not in the schema (#333)


class CurrentVersion(Frozen):
    """The version of a project document a drafter is to regenerate, with any decision on it."""

    version_ref: DocumentVersionRef
    document_title: str | None = None
    media_type: str
    document_text: str
    version_state: VersionState
    decision_reason: str | None = None
    revision_request: str | None = None


class ApprovedMetadataRecord(Frozen):
    """The version of the project's metadata record a person approved last
    (docs/specs/projects.md)."""

    version_ref: DocumentVersionRef
    media_type: str
    conforms_to: str | None = None
    document_text: str


class DraftRequest(Frozen):
    """A project document of one kind to draft from the project's facts (docs/specs/projects.md)."""

    schema_class: Literal["DraftRequest"] = "DraftRequest"
    document_kind: DocumentKind
    inventory: FileInventory | None = None
    requirements: RepositoryRequirements | None = None
    metadata_record: ApprovedMetadataRecord | None = None
    current_version: CurrentVersion | None = None
    # In a project the conductor fills every slot but these two (data_director.yaml says each).
    draft_answers: list[DraftAnswer] = Field(default_factory=list)
    shared_answers: list[SharedAnswer] = Field(default_factory=list)
    redraft_document: str | None = Field(default=None, pattern=UUID7_PATTERN)
    revise: bool = False
    researchers: list[ResearcherRecord] = Field(default_factory=list)
    project_documents: list[ProjectDocument] = Field(default_factory=list)
    project_decisions: list[ProjectFact] = Field(default_factory=list)
    # Filled by the conductor from the profile (`GivenInstitutionStorage`): what a Data
    # Management Plan's storage question may offer (docs/specs/drafting.md).
    institution_storage: list[InstitutionStorage] = Field(default_factory=list)

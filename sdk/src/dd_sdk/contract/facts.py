"""Pydantic mirrors of the facts a project, or the deployment, gives agents
(schema/data_director.yaml, docs/specs/projects.md): what researchers kept from their own public
ORCID records (`ResearcherRecord`), the facts people decided about the project (`ProjectFact`),
the repository a researcher chose (`ChosenRepository`), what its inventory is
(`InventorySummary`), the documents a researcher attached (`DocumentationSummary`, and
`ProjectDocument` with its text), and the repositories and storage services the profile names as
its institution's (`InstitutionRepository`, `InstitutionStorage`). `dd_sdk.contract.models`
re-exports the classes its own classes use."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from dd_sdk.contract.base import (
    RE3DATA_ID_PATTERN,
    REPOSITORY_ID_PATTERN,
    SHA256_PATTERN,
    Frozen,
    backfill_repository_id,
)


class AffiliationKind(StrEnum):
    EMPLOYMENT = "employment"
    EDUCATION = "education"
    QUALIFICATION = "qualification"
    INVITED_POSITION = "invited_position"
    DISTINCTION = "distinction"
    MEMBERSHIP = "membership"
    SERVICE = "service"


class ResearcherLink(Frozen):
    link_title: str | None = None
    link_url: str


class ExternalIdentifier(Frozen):
    identifier_type: str
    identifier_value: str
    identifier_url: str | None = None


class Affiliation(Frozen):
    put_code: str
    affiliation_kind: AffiliationKind
    organisation_name: str
    organisation_identifier: str | None = None
    organisation_identifier_scheme: str | None = None
    department: str | None = None
    role_title: str | None = None
    start_year: int | None = None
    end_year: int | None = None


class ResearcherWork(Frozen):
    put_code: str
    work_title: str
    work_type: str | None = None
    publication_year: int | None = None
    journal_title: str | None = None
    work_identifiers: list[ExternalIdentifier] = Field(default_factory=list)


class ResearcherFunding(Frozen):
    put_code: str
    funding_title: str
    funding_type: str | None = None
    funder_name: str
    funder_identifier: str | None = None
    funder_identifier_scheme: str | None = None
    award_identifier: str | None = None
    start_year: int | None = None
    end_year: int | None = None


class ResearcherRecord(Frozen):
    """What one researcher in a project chose to keep from their public ORCID record, in ORCID's
    own words (docs/specs/projects.md). Never an email address."""

    orcid_id: str
    researcher_name: str | None = None
    other_names: list[str] = Field(default_factory=list)
    biography: str | None = None
    keywords: list[str] = Field(default_factory=list)
    country: list[str] = Field(default_factory=list)
    researcher_links: list[ResearcherLink] = Field(default_factory=list)
    external_identifiers: list[ExternalIdentifier] = Field(default_factory=list)
    affiliations: list[Affiliation] = Field(default_factory=list)
    works: list[ResearcherWork] = Field(default_factory=list)
    works_omitted: int | None = None
    fundings: list[ResearcherFunding] = Field(default_factory=list)
    record_retrieved_at: datetime
    record_source: str


class FactKind(StrEnum):
    """What a project fact is about (docs/specs/projects.md)."""

    FUNDER = "funder"
    REQUIRED_REPOSITORY = "required_repository"
    FILE_INCLUSION = "file_inclusion"
    SENSITIVITY = "sensitivity"
    LICENCE = "licence"
    SHARING_COMMITMENT = "sharing_commitment"
    STANDARD = "standard"
    DATA_MANAGEMENT_PLAN = "data_management_plan"
    DATA_DESCRIPTION = "data_description"


class FileDecision(StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    UNDECIDED = "undecided"


class SensitivityDecision(StrEnum):
    PUBLISH = "publish"
    GENERALISE = "generalise"
    WITHHOLD = "withhold"
    UNDECIDED = "undecided"


class StandardKind(StrEnum):
    """What kind of standard a `standard` fact names."""

    METADATA_STANDARD = "metadata_standard"
    CONTROLLED_VOCABULARY = "controlled_vocabulary"
    ONTOLOGY = "ontology"
    TERMINOLOGY = "terminology"
    DATA_FORMAT = "data_format"
    FIELD_FORMAT = "field_format"


class LocationPrecision(StrEnum):
    EXACT = "exact"
    SITE = "site"
    REGION = "region"
    COUNTRY = "country"


# What a standard is chosen for: the dataset, or one field of its tables.
STANDARD_TARGET_PATTERN = r"^(dataset|field:\S.*)$"
DATASET_TARGET = "dataset"

# The one subject a `data_management_plan` or `data_description` fact has, so that a project has
# at most one current plan and one description: the last decision on each stands
# (docs/specs/projects.md, invariant 32).
PLAN_SUBJECT = "project"
# The kinds of fact whose subject is always `PLAN_SUBJECT`.
PROJECT_WIDE = frozenset({FactKind.DATA_MANAGEMENT_PLAN, FactKind.DATA_DESCRIPTION})

# The value slots each kind of project fact needs (the schema's rules on ProjectFact).
FACT_NEEDS: dict[FactKind, tuple[str, ...]] = {
    FactKind.FUNDER: ("fact_funder_name",),
    FactKind.REQUIRED_REPOSITORY: ("fact_repository_name",),
    FactKind.FILE_INCLUSION: ("fact_file_path", "file_decision"),
    FactKind.SENSITIVITY: ("sensitive_subject", "sensitivity_decision"),
    FactKind.LICENCE: ("licence_id",),
    FactKind.SHARING_COMMITMENT: ("commitment_quote", "commitment_document"),
    FactKind.STANDARD: ("standard_name",),
    FactKind.DATA_MANAGEMENT_PLAN: ("plan_document",),
    FactKind.DATA_DESCRIPTION: ("data_collected",),
}


class ProjectFact(Frozen):
    """One fact about a project that an agent proposes and a person decides
    (docs/specs/projects.md). `fact_kind` says which value slots apply; the last decision on a
    kind and `fact_subject` stands."""

    fact_kind: FactKind
    fact_subject: str = Field(pattern=r"\S")
    fact_funder_name: str | None = None
    fact_funder_ror: str | None = None
    fact_crossref_funder_id: str | None = None
    fact_repository_name: str | None = None
    fact_re3data_id: str | None = Field(default=None, pattern=RE3DATA_ID_PATTERN)
    fact_required_by: list[str] = Field(default_factory=list)
    fact_file_path: str | None = Field(default=None, pattern=r"^[^/]")
    file_decision: FileDecision | None = None
    fact_check_kind: str | None = None
    sensitive_subject: str | None = None
    sensitivity_decision: SensitivityDecision | None = None
    location_precision: LocationPrecision | None = None
    licence_id: str | None = None
    # A sharing commitment: as the plan states it, quoted from the attached document it names.
    commitment_repository: str | None = None
    commitment_access: str | None = None
    commitment_licence: str | None = None
    commitment_quote: str | None = None
    commitment_document: str | None = Field(default=None, pattern=SHA256_PATTERN)
    # A standard, vocabulary or format chosen; `standard_target` is dataset or field:<name>.
    standard_name: str | None = None
    standard_id: str | None = None
    standard_kind: StandardKind | None = None
    standard_target: str | None = Field(default=None, pattern=STANDARD_TARGET_PATTERN)
    # Which attached document is the project's data management plan, by its text's digest.
    plan_document: str | None = Field(default=None, pattern=SHA256_PATTERN)
    # What data the project collects and how, in the researcher's words (`data_description`).
    data_collected: str | None = None
    data_collection_method: str | None = None
    data_formats: str | None = None
    data_volume: str | None = None
    data_reused: str | None = None
    # Shown to the person deciding; never given to an agent.
    proposed_because: str | None = None

    @model_validator(mode="after")
    def _has_what_its_kind_needs(self) -> ProjectFact:
        missing = [slot for slot in FACT_NEEDS[self.fact_kind] if getattr(self, slot) is None]
        if missing:
            raise ValueError(f"a {self.fact_kind} fact needs {', '.join(missing)}")
        if self.fact_kind in PROJECT_WIDE and self.fact_subject != PLAN_SUBJECT:
            raise ValueError(f"a {self.fact_kind} fact's subject is {PLAN_SUBJECT!r}")
        return self


class DocumentKind(StrEnum):
    METADATA_RECORD = "metadata_record"
    README = "readme"
    DATA_DICTIONARY = "data_dictionary"
    DMP = "dmp"
    OTHER = "other"


class VersionState(StrEnum):
    """The state of one version of a project document (docs/specs/projects.md)."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class InventoryFormat(Frozen):
    """The files of one media type in a project's inventory, without their paths."""

    format_media_type: str | None = None
    format_pronom_ids: list[str] = Field(default_factory=list)
    format_file_count: int


class InventorySummary(Frozen):
    """What the inventory a project holds is, without its files (docs/specs/projects.md)."""

    inventory_digest: str = Field(pattern=SHA256_PATTERN)
    inventory_file_count: int
    inventory_tool: str
    inventory_tool_version: str
    inventory_made_at: datetime
    inventory_limitations: list[str] = Field(default_factory=list)
    # When it was added to the project, and how many files the inventory it replaced listed.
    inventory_added_at: datetime | None = None
    inventory_revised_from_file_count: int | None = None
    inventory_formats: list[InventoryFormat] = Field(default_factory=list)
    inventory_table_count: int | None = None


class DraftSummary(Frozen):
    """The latest version of one document drafted in a project, without its text
    (docs/specs/projects.md)."""

    document_kind: DocumentKind
    version: int
    version_state: VersionState
    # Absent when the project holds no inventory.
    drafted_since_inventory: bool | None = None


class ChosenRepository(Frozen):
    """The repository a researcher chose for the project, as the conductor gives it
    (docs/specs/projects.md). The last choice stands. `chosen_repository_id` is its re3data
    identifier where re3data lists it, else its DataCite repository identifier; a choice recorded
    before there was one names only `chosen_re3data_id`, which then gives it."""

    chosen_repository_name: str
    chosen_repository_id: str = Field(pattern=REPOSITORY_ID_PATTERN)
    chosen_re3data_id: str | None = Field(default=None, pattern=RE3DATA_ID_PATTERN)

    _backfill = model_validator(mode="before")(
        backfill_repository_id("chosen_repository_id", "chosen_re3data_id")
    )


class DocumentationSummary(Frozen):
    """What one document attached to a project is, without its text (docs/specs/projects.md)."""

    documentation_name: str
    documentation_digest: str = Field(pattern=SHA256_PATTERN)
    documentation_media_type: str
    documentation_size: int
    documentation_added_at: datetime
    # The Word or PDF file's media type, for a document whose text was read from one.
    documentation_source_media_type: str | None = None
    # True for the document a person decided is the project's data management plan; filled only
    # by the conductor (docs/specs/projects.md, invariant 32).
    documentation_is_plan: bool | None = None


class ProjectDocument(DocumentationSummary):
    """One document attached to a project, with its text, as a drafter is given it
    (docs/specs/projects.md). The text is the researcher's and untrusted."""

    documentation_text: str


class InstitutionRepository(Frozen):
    """One repository the deployment's profile names as its institution's
    (`institution_repositories`, docs/specs/policy-and-identity.md), as the conductor gives it to
    an agent whose input mixes in `GivenInstitutionRepositories`. It names a registry's record by
    `repository_id` and adds only what the deployment vouches for that no registry holds;
    `profile_ref` is the reference of the profile, under which an agent cites those facts."""

    repository_id: str = Field(pattern=REPOSITORY_ID_PATTERN)
    profile_ref: str = Field(pattern=r"^profile:\S+@v[0-9]+$")
    institution_name: str | None = None
    institution_ror: str | None = None
    data_access_types: list[str] = Field(default_factory=list)
    data_licences: list[str] = Field(default_factory=list)
    charges_deposit_fee: bool | None = None
    guidance: list[str] = Field(default_factory=list)


class StorageKind(StrEnum):
    INSTITUTIONAL_FILESTORE = "institutional_filestore"
    INSTITUTIONAL_CLOUD = "institutional_cloud"
    MANAGED_CLOUD = "managed_cloud"
    SECURE_ENVIRONMENT = "secure_environment"


# A deployment's own label for a storage service.
STORAGE_ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


class InstitutionStorage(Frozen):
    """One storage service the deployment's profile names as its institution's, for keeping data
    while a project runs (`institution_storage`, docs/specs/policy-and-identity.md), as the
    conductor gives it to an agent whose input mixes in `GivenInstitutionStorage`. It holds only
    what the deployment vouches for; `profile_ref` is the reference of the profile, under which
    an agent cites it. An unknown `approved_for_sensitive` is never taken as approval."""

    storage_id: str = Field(pattern=STORAGE_ID_PATTERN)
    profile_ref: str = Field(pattern=r"^profile:\S+@v[0-9]+$")
    storage_name: str
    storage_description: str | None = None
    storage_kind: StorageKind | None = None
    approved_for_sensitive: bool | None = None
    allows_external_collaborators: bool | None = None
    # A float so that it hashes the same after A2A's Struct, which has no integers.
    allowance_gb: float | None = Field(default=None, ge=0)
    charges_for_storage: bool | None = None
    storage_backup: str | None = None
    guidance: list[str] = Field(default_factory=list)

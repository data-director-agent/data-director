"""Pydantic mirrors of the facts a project gives agents (schema/data_director.yaml,
docs/specs/projects.md): what researchers kept from their own public ORCID records
(`ResearcherRecord`), the facts people decided about the project (`ProjectFact`), and the
documents a researcher attached (`DocumentationSummary`, and `ProjectDocument` with its text).
`dd_sdk.contract.models` re-exports the classes its own classes use."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from dd_sdk.contract.base import SHA256_PATTERN, Frozen


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


class FileDecision(StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    UNDECIDED = "undecided"


class SensitivityDecision(StrEnum):
    PUBLISH = "publish"
    GENERALISE = "generalise"
    WITHHOLD = "withhold"
    UNDECIDED = "undecided"


class LocationPrecision(StrEnum):
    EXACT = "exact"
    SITE = "site"
    REGION = "region"
    COUNTRY = "country"


# The value slots each kind of project fact needs (the schema's rules on ProjectFact).
FACT_NEEDS: dict[FactKind, tuple[str, ...]] = {
    FactKind.FUNDER: ("fact_funder_name",),
    FactKind.REQUIRED_REPOSITORY: ("fact_repository_name",),
    FactKind.FILE_INCLUSION: ("fact_file_path", "file_decision"),
    FactKind.SENSITIVITY: ("sensitive_subject", "sensitivity_decision"),
    FactKind.LICENCE: ("licence_id",),
    FactKind.SHARING_COMMITMENT: ("commitment_quote", "commitment_document"),
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
    fact_re3data_id: str | None = Field(default=None, pattern=r"^r3d[0-9]{9}$")
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
    # Shown to the person deciding; never given to an agent.
    proposed_because: str | None = None

    @model_validator(mode="after")
    def _has_what_its_kind_needs(self) -> ProjectFact:
        missing = [slot for slot in FACT_NEEDS[self.fact_kind] if getattr(self, slot) is None]
        if missing:
            raise ValueError(f"a {self.fact_kind} fact needs {', '.join(missing)}")
        return self


class DocumentationSummary(Frozen):
    """What one document attached to a project is, without its text (docs/specs/projects.md)."""

    documentation_name: str
    documentation_digest: str = Field(pattern=SHA256_PATTERN)
    documentation_media_type: str
    documentation_size: int
    documentation_added_at: datetime
    # The Word or PDF file's media type, for a document whose text was read from one.
    documentation_source_media_type: str | None = None


class ProjectDocument(DocumentationSummary):
    """One document attached to a project, with its text, as a drafter is given it
    (docs/specs/projects.md). The text is the researcher's and untrusted."""

    documentation_text: str

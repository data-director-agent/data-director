"""Pydantic mirrors of the LinkML classes for what a researcher kept from their public ORCID
record (schema/data_director.yaml, docs/specs/projects.md). `dd_sdk.contract.models` re-exports
them, so code imports them from there.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from dd_sdk.contract.base import Frozen


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

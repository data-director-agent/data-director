"""What the project's researchers kept of their public ORCID records, written into the record
(docs/specs/projects.md, invariant 27): each researcher as a creator, with their iD and current
employers, their keywords as subjects, and their grants as funding references, wherever the
repository asks for those properties."""

from __future__ import annotations

from typing import Any

from dd_sdk.contract.models import (
    Affiliation,
    AffiliationKind,
    ResearcherFunding,
    ResearcherRecord,
)

# DataCite's names for the identifier schemes ORCID gives funders in.
FUNDER_SCHEMES = {"FUNDREF": "Crossref Funder ID", "ROR": "ROR", "GRID": "GRID", "ISNI": "ISNI"}
SCHEME_URIS = {"ROR": "https://ror.org", "GRID": "https://www.grid.ac", "ISNI": "https://isni.org"}


def fill(record: dict[str, Any], researchers: list[ResearcherRecord]) -> list[str]:
    """Fill the creators, subjects and funding references the repository asks for from what the
    project's researchers kept of their ORCID records; returns the properties filled. A property
    the record does not have, because the repository does not ask for it, is left out."""
    filled: list[str] = []
    if not researchers:
        return filled
    if "creators" in record:
        record["creators"] = [_creator(r) for r in researchers]
        filled.append("creators")
    keywords = list(dict.fromkeys(k for r in researchers for k in r.keywords))
    if "subjects" in record and keywords:
        # The researchers' own words, after the entries the repository's vocabularies ask for.
        asked = [s for s in record["subjects"] if s.get("subjectScheme")]
        record["subjects"] = [*asked, *({"subject": k} for k in keywords)]
        filled.append("subjects")
    fundings = [f for r in researchers for f in r.fundings]
    if "fundingReferences" in record and fundings:
        record["fundingReferences"] = [_funding(f) for f in fundings]
        filled.append("fundingReferences")
    return filled


def _creator(researcher: ResearcherRecord) -> dict[str, Any]:
    """One researcher as a DataCite creator: their name, if they kept it (else null, for them to
    write), their ORCID iD, and the employers they kept that they still work for."""
    creator: dict[str, Any] = {
        "name": researcher.researcher_name,
        "nameType": "Personal",
        "nameIdentifiers": [
            {
                "nameIdentifier": researcher.orcid_id,
                "nameIdentifierScheme": "ORCID",
                "schemeUri": "https://orcid.org",
            }
        ],
    }
    current = [
        a
        for a in researcher.affiliations
        if a.affiliation_kind == AffiliationKind.EMPLOYMENT and a.end_year is None
    ]
    if current:
        creator["affiliation"] = [_affiliation(a) for a in current]
    return creator


def _affiliation(affiliation: Affiliation) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": affiliation.organisation_name}
    scheme = (affiliation.organisation_identifier_scheme or "").upper()
    if affiliation.organisation_identifier:
        entry["affiliationIdentifier"] = affiliation.organisation_identifier
        entry["affiliationIdentifierScheme"] = affiliation.organisation_identifier_scheme
        if scheme in SCHEME_URIS:
            entry["schemeUri"] = SCHEME_URIS[scheme]
    return entry


def _funding(funding: ResearcherFunding) -> dict[str, Any]:
    entry: dict[str, Any] = {"funderName": funding.funder_name}
    if funding.funder_identifier:
        entry["funderIdentifier"] = funding.funder_identifier
        scheme = (funding.funder_identifier_scheme or "").upper()
        entry["funderIdentifierType"] = FUNDER_SCHEMES.get(scheme, "Other")
    if funding.award_identifier:
        entry["awardNumber"] = funding.award_identifier
    entry["awardTitle"] = funding.funding_title
    return entry

"""What the project's researchers kept of their public ORCID records, written into the record
(docs/specs/projects.md, invariant 27): each researcher as a creator, with their iD and current
employers, their keywords as subjects, and their grants as funding references, wherever the
repository asks for those properties.

Each is given as a node of the pivot, in its terms (docs/specs/metadata-standards.md), and written
into the record's own keys by its standard's definition, so this module names no property of any
standard. A part the standard has no key for is left out.
"""

from __future__ import annotations

from typing import Any, Final

from dd_metadata_records import Definition, Node, entry, get_path, has_path, set_path
from dd_sdk.contract.models import (
    Affiliation,
    AffiliationKind,
    ResearcherFunding,
    ResearcherRecord,
)

SCHEMA: Final = "http://schema.org/"
CREATOR: Final = SCHEMA + "creator"
KEYWORDS: Final = SCHEMA + "keywords"
FUNDING: Final = SCHEMA + "funding"
IDENTIFIER: Final = SCHEMA + "identifier"
SCHEME: Final = SCHEMA + "propertyID"
URL: Final = SCHEMA + "url"
AFFILIATION: Final = SCHEMA + "affiliation"
TITLE: Final = SCHEMA + "name"
AWARD: Final = SCHEMA + "termCode"
KIND: Final = "http://purl.org/dc/terms/type"
# The names of the identifier schemes ORCID gives funders in, as DataCite's vocabulary has them.
FUNDER_SCHEMES = {"FUNDREF": "Crossref Funder ID", "ROR": "ROR", "GRID": "GRID", "ISNI": "ISNI"}
SCHEME_URIS = {"ROR": "https://ror.org", "GRID": "https://www.grid.ac", "ISNI": "https://isni.org"}


def fill(
    record: dict[str, Any], researchers: list[ResearcherRecord], definition: Definition
) -> list[str]:
    """Fill the creators, subjects and funding references the repository asks for from what the
    project's researchers kept of their ORCID records; returns the properties filled, by path. A
    property the record does not have, because the repository does not ask for it, is left
    out."""
    filled: list[str] = []
    if not researchers:
        return filled
    creators = definition.property_for(CREATOR)
    if creators is not None and has_path(record, creators.path):
        set_path(record, creators.path, [entry(creators, _creator(r)) for r in researchers])
        filled.append(creators.path)
    keywords = list(dict.fromkeys(k for r in researchers for k in r.keywords))
    subjects = definition.property_for(KEYWORDS)
    if subjects is not None and has_path(record, subjects.path) and keywords:
        # The researchers' own words, after the entries the repository's vocabularies ask for.
        given = get_path(record, subjects.path)
        asked = [
            s
            for s in (given if isinstance(given, list) else [])
            if isinstance(s, dict) and subjects.term_for(s) != KEYWORDS
        ]
        words = [entry(subjects, Node(subjects.path, k)) for k in keywords]
        set_path(record, subjects.path, [*asked, *words])
        filled.append(subjects.path)
    fundings = [f for r in researchers for f in r.fundings]
    funding = definition.property_for(FUNDING)
    if funding is not None and has_path(record, funding.path) and fundings:
        set_path(record, funding.path, [entry(funding, _funding(f)) for f in fundings])
        filled.append(funding.path)
    return filled


def _creator(researcher: ResearcherRecord) -> Node:
    """One researcher as a creator: their name, if they kept it (else a gap, for them to write),
    their ORCID iD, and the employers they kept that they still work for."""
    orcid = Node(
        "",
        researcher.orcid_id,
        {SCHEME: (Node("", "ORCID"),), URL: (Node("", "https://orcid.org"),)},
    )
    parts: dict[str, tuple[Node, ...]] = {KIND: (Node("", "Personal"),), IDENTIFIER: (orcid,)}
    current = [
        a
        for a in researcher.affiliations
        if a.affiliation_kind == AffiliationKind.EMPLOYMENT and a.end_year is None
    ]
    if current:
        parts[AFFILIATION] = tuple(_affiliation(a) for a in current)
    return Node("", researcher.researcher_name, parts)


def _affiliation(affiliation: Affiliation) -> Node:
    parts: dict[str, tuple[Node, ...]] = {}
    scheme = (affiliation.organisation_identifier_scheme or "").upper()
    if affiliation.organisation_identifier:
        parts[IDENTIFIER] = (Node("", affiliation.organisation_identifier),)
        parts[SCHEME] = (Node("", affiliation.organisation_identifier_scheme),)
        if scheme in SCHEME_URIS:
            parts[URL] = (Node("", SCHEME_URIS[scheme]),)
    return Node("", affiliation.organisation_name, parts)


def _funding(funding: ResearcherFunding) -> Node:
    parts: dict[str, tuple[Node, ...]] = {}
    if funding.funder_identifier:
        parts[IDENTIFIER] = (Node("", funding.funder_identifier),)
        scheme = (funding.funder_identifier_scheme or "").upper()
        parts[SCHEME] = (Node("", FUNDER_SCHEMES.get(scheme, "Other")),)
    if funding.award_identifier:
        parts[AWARD] = (Node("", funding.award_identifier),)
    parts[TITLE] = (Node("", funding.funding_title),)
    return Node("", funding.funder_name, parts)

"""A grant number, as the grant resolver found it: every grant it may name, as candidates.

The resolver (`grants.resolve_grant`) answers one record for each grant the number may name. The
link lists each as a candidate and cites each record. With one, the link takes its title and the
advice spells out the DataCite funding reference to record. With more than one, the link has no
title and asks the researcher to choose: the adviser never picks a grant for them, since the number
alone cannot tell them apart.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from dd_agent_advisor_linking.classes import GrantCandidate, RelatedLink
from dd_sdk.tools import ToolRecord

CROSSREF_FUNDER = "https://doi.org/10.13039/"
ROR = "https://ror.org/"
GRANT_TYPE = "Grant"

FOUND_ONE = (
    "Found one grant with this number, through {server}: check it is your grant. Record it as a "
    "funding reference: funderName {funder}{identifier}, awardNumber {award}{title}{uri}."
)
FOUND_MANY = (
    "Found {count} grants with this number, through {server}, from {funders}. The number alone "
    "cannot tell them apart: choose yours from the candidates, by its funder, and record that one "
    "as a funding reference (funderName, funderIdentifier, awardNumber, awardTitle). The adviser "
    "does not choose for you."
)


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _funder_identifier(content: Mapping[str, Any]) -> str | None:
    """The funder's Crossref Funder ID if the record gives one, else its ROR id."""
    ids = [i for i in content.get("funder_ids") or [] if isinstance(i, str)]
    for prefix in (CROSSREF_FUNDER, ROR):
        if found := next((i for i in ids if i.startswith(prefix)), None):
            return found
    return None


def _identifier_type(identifier: str) -> str:
    return "Crossref Funder ID" if identifier.startswith(CROSSREF_FUNDER) else "ROR"


def candidate(content: Mapping[str, Any]) -> GrantCandidate:
    """One grant record as a candidate."""
    return GrantCandidate(
        id=str(content.get("id")),
        award=_text(content.get("award")),
        title=_text(content.get("title")),
        funder=_text(content.get("funder")),
        funder_identifier=_funder_identifier(content),
        funding_stream=_text(content.get("funding_stream")),
        source=_text(content.get("source")) or "unknown",
    )


def _doi_url(content: Mapping[str, Any]) -> str | None:
    doi = _text(content.get("doi"))
    return f"https://doi.org/{doi}" if doi else None


def _one(link: RelatedLink, server: str, record: ToolRecord, grant: GrantCandidate) -> RelatedLink:
    ident = grant.funder_identifier
    identifier = f", funderIdentifier {ident} ({_identifier_type(ident)})" if ident else ""
    title = f", awardTitle {grant.title!r}" if grant.title else ""
    uri = _doi_url(record.content)
    message = FOUND_ONE.format(
        server=server,
        funder=grant.funder or "(not given: add the funder's name)",
        identifier=identifier,
        award=grant.award or link.given.strip(),
        title=title,
        uri=f", awardURI {uri}" if uri else "",
    )
    return link.model_copy(
        update={
            "resolved": True,
            "normalised": uri,
            "title": grant.title,
            "resource_type": GRANT_TYPE,
            "candidates": [grant],
            "message": message,
        }
    )


def _listed(names: Iterable[str]) -> str:
    named = list(dict.fromkeys(names))
    return named[0] if len(named) == 1 else f"{', '.join(named[:-1])} and {named[-1]}"


def found(link: RelatedLink, server: str, records: tuple[ToolRecord, ...]) -> RelatedLink:
    """`link`, a grant number, with every grant `server` found for it as a candidate."""
    grants = [candidate(r.content) for r in records]
    if len(grants) == 1:
        return _one(link, server, records[0], grants[0])
    funders = _listed(g.funder or "a funder not named" for g in grants)
    message = FOUND_MANY.format(count=len(grants), server=server, funders=funders)
    return link.model_copy(
        update={
            "resolved": True,
            "resource_type": GRANT_TYPE,
            "candidates": grants,
            "message": message,
        }
    )

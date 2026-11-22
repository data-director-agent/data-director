"""Resolving identifiers through the harness's tool gateway (docs/specs/agents.md, Tools).

Which sources exist is the deployment's choice: its tool configuration lists the MCP servers and
its profile grants them to this agent. In the Data Director they are the PID resolver's
(mcp-pid/README.md). The card declares, for each scheme, the servers to ask in order and the one
tool each offers:

- a DOI: `datacite.get_doi`, then `crossref.get_doi`, since each agency holds only the DOIs it
  registered, so a DOI DataCite does not hold is asked of Crossref;
- an ORCID iD: `orcid.get_orcid`;
- a ROR id: `ror.get_organisation`.

A DOI once found is given the relation that suits the type of work its record names
(`relations.yaml`); one not found keeps the scheme's default.

Of those the gateway lists for the invocation, each is called with the identifier and answers
`{"records": [...]}`: one record when found, none when not. The conductor records each record, and
the link cites exactly the one it was resolved against. A lookup that fails, errors or finds
nothing is noted on the link and never raised.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dd_agent_advisor_linking import relations
from dd_agent_advisor_linking.classes import RelatedLink
from dd_sdk.tools import ToolGatewayError, ToolRecord, Tools, ToolUse, split_name

DOI_TOOL = "get_doi"
ORCID_TOOL = "get_orcid"
ROR_TOOL = "get_organisation"
DOI_PREFIX = "https://doi.org/"

FORM_ONLY = "Recognised by form only, not resolved."
NOT_FOUND = "Not found by {servers}: check it for a typing error."
FAILED = "Could not be looked up through {servers}, so it is recorded by form only."
RESOLVED = "Found through {server}: check {what}."
FUNDER = (
    "Its Crossref Funder ID is {id}: where a repository asks for one, record "
    "https://doi.org/10.13039/{id} as the funderIdentifier, of type Crossref Funder ID."
)


@dataclass(frozen=True)
class Route:
    """How one scheme is resolved: the servers to ask, in order, and the tool and argument."""

    scheme: str
    label: str
    servers: tuple[str, ...]
    tool: str
    argument: str
    check: str  # what the researcher checks once it is found


ROUTES = (
    Route(
        "doi",
        "DOIs",
        ("datacite", "crossref"),
        DOI_TOOL,
        "doi",
        "the title and type are what you mean to link",
    ),
    Route("orcid", "ORCID iDs", ("orcid",), ORCID_TOOL, "orcid", "this is the person you mean"),
    Route("ror", "ROR ids", ("ror",), ROR_TOOL, "id", "this is the organisation you mean"),
)
BY_SCHEME = {route.scheme: route for route in ROUTES}
TOOLS = tuple(ToolUse(server, (r.tool,)) for r in ROUTES for server in r.servers)
NAMES = {"datacite": "DataCite", "crossref": "Crossref", "orcid": "ORCID", "ror": "ROR"}


@dataclass(frozen=True)
class Lookup:
    """What looking up one identifier came to: the link updated, and the record it cites."""

    link: RelatedLink
    record: ToolRecord | None = None


def available(tools: Tools | None) -> dict[str, tuple[str, ...]]:
    """For each scheme, the servers the gateway lists as offering its tool, in the order to ask
    them. A scheme with none is left out."""
    if tools is None:
        return {}
    try:
        listed = tools.listed()
    except ToolGatewayError:
        return {}
    offered: set[tuple[str, str]] = set()
    for tool in listed:
        try:
            offered.add(split_name(str(tool.get("name"))))
        except ValueError:
            continue
    out: dict[str, tuple[str, ...]] = {}
    for route in ROUTES:
        if servers := tuple(s for s in route.servers if (s, route.tool) in offered):
            out[route.scheme] = servers
    return out


def lookup(tools: Tools, servers: tuple[str, ...], link: RelatedLink) -> Lookup:
    """`link`, a well-formed identifier, asked of each of `servers` in turn until one finds it."""
    route = BY_SCHEME[link.scheme]
    assert link.normalised is not None
    value = link.normalised.removeprefix(DOI_PREFIX) if route.scheme == "doi" else link.normalised
    failed: list[str] = []
    for server in servers:
        try:
            outcome = tools.call(server, route.tool, {route.argument: value})
        except ToolGatewayError:
            failed.append(server)
            continue
        if outcome.is_error:
            failed.append(server)
            continue
        if outcome.records:
            record = outcome.records[0]
            return Lookup(_found(link, route, server, record.content), record)
    if failed and len(failed) == len(servers):
        return Lookup(_noted(link, FAILED.format(servers=_names(failed, "and"))))
    return Lookup(_noted(link, NOT_FOUND.format(servers=_names(servers, "or"))))


def _found(link: RelatedLink, route: Route, server: str, content: Mapping[str, Any]) -> RelatedLink:
    """`link` as the record `server` found describes it. A DOI's relation is suggested from the
    type of work the record names, where the relation table knows it (relations.py); a ROR id's
    Crossref Funder ID, where it has one, is added to the advice."""
    title, resource_type = _described(route.scheme, content)
    update: dict[str, Any] = {"resolved": True, "title": title, "resource_type": resource_type}
    advice = _advice(link)
    if route.scheme == "doi" and (row := relations.for_type(resource_type)) is not None:
        update["relation"] = row.relation
        advice = row.advice
    elif route.scheme == "ror" and (funder := _funder_id(content)):
        advice = f"{advice} {FUNDER.format(id=funder)}"
    found = RESOLVED.format(server=NAMES.get(server, server), what=route.check)
    update["message"] = f"{found} {advice}"
    return link.model_copy(update=update)


def _funder_id(content: Mapping[str, Any]) -> str | None:
    return _text(content.get("crossref_funder_preferred")) or _text(
        content.get("crossref_funder_ids")
    )


def _described(scheme: str, content: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """The title and type a found record gives the link."""
    if scheme == "orcid":
        given = " ".join(
            n for n in (_text(content.get("given_names")), _text(content.get("family_name"))) if n
        )
        return _text(content.get("credit_name")) or given or None, "Person"
    if scheme == "ror":
        return _label(content), _text(content.get("types"))
    return _text(content.get("title")), _text(content.get("type"))


def _label(content: Mapping[str, Any]) -> str | None:
    names = [n for n in content.get("names") or [] if isinstance(n, Mapping)]
    for wanted in ("ror_display", "label"):
        for name in names:
            if wanted in (name.get("types") or []):
                return _text(name.get("value"))
    return _text(names[0].get("value")) if names else None


def _names(servers: tuple[str, ...] | list[str], joiner: str) -> str:
    named = [NAMES.get(s, s) for s in servers]
    return named[0] if len(named) == 1 else f"{', '.join(named[:-1])} {joiner} {named[-1]}"


def _advice(link: RelatedLink) -> str:
    return link.message.removeprefix(FORM_ONLY).strip()


def _noted(link: RelatedLink, message: str) -> RelatedLink:
    return link.model_copy(update={"resolved": False, "message": f"{message} {_advice(link)}"})


def _text(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, str) and value else None


def cited(lookups: list[Lookup]) -> list[ToolRecord]:
    """The records the lookups found, once each."""
    by_hash: Mapping[str, ToolRecord] = {
        lk.record.content_hash: lk.record for lk in lookups if lk.record is not None
    }
    return list(by_hash.values())

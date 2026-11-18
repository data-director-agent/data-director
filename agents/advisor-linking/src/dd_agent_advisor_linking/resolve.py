"""Resolving DOIs through the harness's tool gateway (docs/specs/agents.md, Tools).

Which sources exist is the deployment's choice: its tool configuration lists the MCP servers and
its profile grants them to this agent. The convention this module reads is small. The card declares
the servers in `SERVERS`, each with the one tool `get_doi`; of those the gateway lists for the
invocation, the first server offering `get_doi` is called with `{"doi": "<bare DOI>"}`. The tool
returns one structured record with a `title` (a string, or a list whose first item is used) and a
`type`; the conductor records the record, and the link cites exactly that one. A lookup that fails,
errors or finds nothing is noted on the link and never raised.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dd_agent_advisor_linking.classes import RelatedLink
from dd_sdk.tools import ToolGatewayError, ToolRecord, Tools, ToolUse, split_name

DOI_TOOL = "get_doi"
SERVERS = ("crossref", "datacite")
TOOLS = tuple(ToolUse(server, (DOI_TOOL,)) for server in SERVERS)
DOI_PREFIX = "https://doi.org/"

FORM_ONLY = "Recognised by form only, not resolved."
NOT_FOUND = "The DOI was not found by {server}: check it for a typing error."
FAILED = "The DOI could not be looked up through {server}, so it is recorded by form only."
RESOLVED = "Found through {server}: check the title and type are what you mean to link."


@dataclass(frozen=True)
class Lookup:
    """What looking up one DOI came to: the link updated, and the record it cites, if any."""

    link: RelatedLink
    record: ToolRecord | None = None


def doi_server(tools: Tools | None) -> str | None:
    """The first server the gateway lists as offering `get_doi`, or None."""
    if tools is None:
        return None
    try:
        listed = tools.listed()
    except ToolGatewayError:
        return None
    for tool in listed:
        try:
            server, name = split_name(str(tool.get("name")))
        except ValueError:
            continue
        if name == DOI_TOOL and server in SERVERS:
            return server
    return None


def lookup(tools: Tools, server: str, link: RelatedLink) -> Lookup:
    """`link`, a well-formed DOI, looked up on `server`."""
    assert link.normalised is not None
    doi = link.normalised.removeprefix(DOI_PREFIX)
    try:
        outcome = tools.call(server, DOI_TOOL, {"doi": doi})
    except ToolGatewayError:
        return Lookup(_noted(link, FAILED.format(server=server)))
    if outcome.is_error:
        return Lookup(_noted(link, FAILED.format(server=server)))
    if not outcome.records:
        return Lookup(_noted(link, NOT_FOUND.format(server=server)))
    record = outcome.records[0]
    update = {
        "resolved": True,
        "title": _text(record.content.get("title")),
        "resource_type": _text(record.content.get("type")),
        "message": f"{RESOLVED.format(server=server)} {_advice(link)}",
    }
    return Lookup(link.model_copy(update=update), record)


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

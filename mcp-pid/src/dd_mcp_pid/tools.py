"""The tools each registry's MCP server offers, and how a call is answered.

Every tool is read-only, takes one identifier or name, and answers `structuredContent` of the form
`{"records": [...]}`, valid against the tool's `outputSchema`, with a one-line summary as text:

- found: the record (or, for a search, every match);
- not found: no records. An MCP client refuses a tool with an output schema that answers with no
  structured content, so a miss is an empty list, not text alone;
- the registry could not be asked, or the input is not an identifier of that kind: `isError`.

The schemas are written out here rather than generated, because a client pins each tool's name,
description and schemas (the Data Director's gateway hashes them): they change only when this
module does, never with a library upgrade. Each record's identifying field is at its top level
(`doi`, `orcid`, `id`), and no record holds an integer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mcp_types import CallToolResult, TextContent, Tool

from dd_mcp_pid.caching import Lookups, OfflineError
from dd_mcp_pid.dois import Crossref, DataCite, DoiRecord, bare_doi
from dd_mcp_pid.http import UnavailableError
from dd_mcp_pid.orcid import Orcid, OrcidRecord, orcid_url
from dd_mcp_pid.ror import RorApi, RorIndex
from dd_mcp_pid.ror_records import Organisation, ror_url

_TEXT = {"type": "string"}
_OPTIONAL_TEXT = {"type": ["string", "null"]}
_TEXTS = {"type": "array", "items": _TEXT}

DOI_RECORD = {
    "type": "object",
    "properties": {
        "doi": _TEXT,
        "agency": {"type": "string", "enum": ["DataCite", "Crossref"]},
        "title": _OPTIONAL_TEXT,
        "type": _OPTIONAL_TEXT,
        "publisher": _OPTIONAL_TEXT,
        "publication_year": _OPTIONAL_TEXT,
        "creators": _TEXTS,
        "url": _OPTIONAL_TEXT,
    },
    "required": [
        "doi",
        "agency",
        "title",
        "type",
        "publisher",
        "publication_year",
        "creators",
        "url",
    ],
    "additionalProperties": False,
}

ORCID_RECORD = {
    "type": "object",
    "properties": {
        "orcid": _TEXT,
        "given_names": _OPTIONAL_TEXT,
        "family_name": _OPTIONAL_TEXT,
        "credit_name": _OPTIONAL_TEXT,
    },
    "required": ["orcid", "given_names", "family_name", "credit_name"],
    "additionalProperties": False,
}

ORGANISATION = {
    "type": "object",
    "properties": {
        "id": _TEXT,
        "names": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"value": _TEXT, "types": _TEXTS, "lang": _OPTIONAL_TEXT},
                "required": ["value", "types", "lang"],
                "additionalProperties": False,
            },
        },
        "types": _TEXTS,
        "status": _TEXT,
        "country_codes": _TEXTS,
        "crossref_funder_ids": _TEXTS,
        "crossref_funder_preferred": _OPTIONAL_TEXT,
        "parents": _TEXTS,
    },
    "required": [
        "id",
        "names",
        "types",
        "status",
        "country_codes",
        "crossref_funder_ids",
        "crossref_funder_preferred",
        "parents",
    ],
    "additionalProperties": False,
}


def records_schema(record: dict[str, Any], *, at_most_one: bool = True) -> dict[str, Any]:
    items: dict[str, Any] = {"type": "array", "items": record}
    if at_most_one:
        items["maxItems"] = 1
    return {
        "type": "object",
        "properties": {"records": items},
        "required": ["records"],
        "additionalProperties": False,
    }


def string_input(name: str, description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {name: {"type": "string", "description": description}},
        "required": [name],
        "additionalProperties": False,
    }


def get_doi_tool(agency: str) -> Tool:
    return Tool(
        name="get_doi",
        description=(
            f"The record {agency} holds for a DOI: title, resource type, publisher, publication "
            f"year, first 25 creators and landing URL. A DOI that {agency} did not register is "
            "not found here: no records."
        ),
        input_schema=string_input("doi", "A DOI, bare (10.xxxx/...) or as a doi.org URL."),
        output_schema=records_schema(DOI_RECORD),
    )


GET_ORCID = Tool(
    name="get_orcid",
    description=(
        "The public name on an ORCID record: given names, family name and published name. A name "
        "the person keeps private is null. No records if ORCID has no such iD."
    ),
    input_schema=string_input(
        "orcid", "An ORCID iD, bare (0000-0000-0000-0000) or as an orcid.org URL."
    ),
    output_schema=records_schema(ORCID_RECORD),
)

GET_ORGANISATION = Tool(
    name="get_organisation",
    description=(
        "An organisation by its ROR identifier: its names, types, status, countries, Crossref "
        "Funder IDs and parent organisations. No records if ROR has no such identifier."
    ),
    input_schema=string_input("id", "A ROR identifier, bare (0xxxxxxNN) or as a ror.org URL."),
    output_schema=records_schema(ORGANISATION),
)

SEARCH_ORGANISATIONS = Tool(
    name="search_organisations",
    description=(
        "The active organisations ROR records under exactly this name, acronym or alias, ignoring "
        "case and spacing. More than one means the name is ambiguous; none means ROR has no such "
        "name."
    ),
    input_schema=string_input("name", "An organisation's name, acronym or alias."),
    output_schema=records_schema(ORGANISATION, at_most_one=False),
)


def found(records: list[dict[str, Any]], summary: str) -> CallToolResult:
    """The records, which may be none, with a summary."""
    return CallToolResult(
        content=[TextContent(type="text", text=summary)],
        structured_content={"records": records},
    )


def text(message: str, *, error: bool = False) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=message)], is_error=error)


type Handler = Callable[[dict[str, Any]], CallToolResult]


@dataclass(frozen=True)
class Registry:
    """One MCP server's worth: its name, its tools and how each is answered."""

    name: str
    tools: tuple[Tool, ...]
    handlers: dict[str, Handler]

    def call(self, tool: str, arguments: dict[str, Any]) -> CallToolResult:
        handler = self.handlers.get(tool)
        if handler is None:
            return text(f"{self.name} has no tool {tool!r}", error=True)
        try:
            return handler(arguments)
        except OfflineError as exc:
            return text(f"{exc}.", error=True)
        except UnavailableError as exc:
            return text(f"{exc}. Try again later.", error=True)


def _arg(arguments: dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    return value if isinstance(value, str) else ""


def _from(source: str) -> str:
    """`source` as a clause after a registry's name: nothing for a live answer."""
    return f", {source}" if source else ""


def _aside(source: str) -> str:
    """`source` in brackets after a miss: nothing for a live answer."""
    return f" ({source})" if source else ""


def _doi_summary(record: DoiRecord, source: str) -> str:
    what = record.type or "work"
    title = record.title or "(untitled)"
    return f"{record.agency}{_from(source)}: {record.doi} ({what}), {title!r}."


def doi_registry(
    agency: str, client: DataCite | Crossref, lookups: Lookups | None = None
) -> Registry:
    """The `datacite` or `crossref` server. Without `lookups`, answers are cached in memory."""
    cached = lookups or Lookups()

    def get_doi(arguments: dict[str, Any]) -> CallToolResult:
        doi = bare_doi(_arg(arguments, "doi"))
        if doi is None:
            return text("Not a DOI: give 10.xxxx/... or a doi.org URL.", error=True)
        record, source = cached.get(agency, doi, DoiRecord, lambda: client.get(doi))
        if record is None:
            return found(
                [], f"{agency} holds no DOI {doi}{_aside(source)}; another registration agency may."
            )
        return found([record.document()], _doi_summary(record, source))

    return Registry(agency.lower(), (get_doi_tool(agency),), {"get_doi": get_doi})


def orcid_registry(client: Orcid, lookups: Lookups | None = None) -> Registry:
    """The `orcid` server. Without `lookups`, answers are cached in memory."""
    cached = lookups or Lookups()

    def get_orcid(arguments: dict[str, Any]) -> CallToolResult:
        url = orcid_url(_arg(arguments, "orcid"))
        if url is None:
            return text("Not an ORCID iD, or its check character is wrong.", error=True)
        record, source = cached.get("ORCID", url, OrcidRecord, lambda: client.get(url))
        if record is None:
            return found([], f"ORCID has no record {url}{_aside(source)}.")
        name = record.credit_name or " ".join(
            n for n in (record.given_names, record.family_name) if n
        )
        who = name or "a person with no public name"
        return found([record.document()], f"ORCID{_from(source)}: {url} is {who}.")

    return Registry("orcid", (GET_ORCID,), {"get_orcid": get_orcid})


@dataclass(frozen=True)
class RorSources:
    """Where ROR is read from: the built registry when there is one, and the API after it. An
    organisation the API gave is kept in `lookups`; offline, `api` is None and only the registry
    and the cache answer."""

    index: RorIndex | None
    api: RorApi | None
    index_label: str = "ROR dump"
    lookups: Lookups = field(default_factory=Lookups)

    def _dump[T](
        self, question: Callable[[RorIndex], T], reasons: list[str]
    ) -> tuple[T, str] | None:
        """The registry's answer, or None (with the reason) when it cannot be read."""
        if self.index is None:
            return None
        try:
            return question(self.index), f"from the {self.index_label}"
        except UnavailableError as exc:
            reasons.append(str(exc))
            return None

    def _api_source(self, reasons: list[str]) -> str:
        return "from ROR's API" + (" (the dump could not be read)" if reasons else "")

    def _no_api(self, reasons: list[str]) -> UnavailableError:
        if self.lookups.offline:
            reasons.append("ROR: this server is offline (DD_PID_OFFLINE), so the API was not asked")
            return OfflineError("; ".join(reasons))
        return UnavailableError("; ".join(reasons) or "ROR: no registry is configured")

    def get(self, url: str) -> tuple[Organisation | None, str]:
        """The organisation, and which copy gave it: the registry, the cache or the API. Raises
        `UnavailableError` when none can answer."""
        reasons: list[str] = []
        if (answer := self._dump(lambda index: index.get(url), reasons)) is not None:
            return answer
        api = self.api
        if api is None and not self.lookups.offline:
            raise self._no_api(reasons)

        def ask() -> Organisation | None:
            if api is None:  # pragma: no cover - offline, the cache asks nothing
                raise self._no_api(reasons)
            return api.get(url)

        try:
            org, cached = self.lookups.get("ROR", url, Organisation, ask)
        except OfflineError as exc:
            raise OfflineError("; ".join([*reasons, str(exc)])) from None
        return org, cached or self._api_source(reasons)

    def find(self, name: str) -> tuple[list[Organisation], str]:
        """The active organisations with this name, and which copy gave them. Searches are not
        cached. Raises `UnavailableError` when no copy can answer."""
        reasons: list[str] = []
        if (answer := self._dump(lambda index: index.find(name), reasons)) is not None:
            return answer
        if self.api is None or self.lookups.offline:
            raise self._no_api(reasons)
        return self.api.find(name), self._api_source(reasons)


def _org_summary(org: Organisation) -> str:
    return f"{org.label} ({org.id}, {', '.join(org.types) or 'organisation'}, {org.status})"


def ror_registry(sources: RorSources) -> Registry:
    """The `ror` server."""

    def get_organisation(arguments: dict[str, Any]) -> CallToolResult:
        url = ror_url(_arg(arguments, "id"))
        if url is None:
            return text("Not a ROR identifier: give 0xxxxxxNN or a ror.org URL.", error=True)
        org, source = sources.get(url)
        if org is None:
            return found([], f"ROR has no organisation {url} ({source}).")
        return found([org.document()], f"ROR, {source}: {_org_summary(org)}.")

    def search_organisations(arguments: dict[str, Any]) -> CallToolResult:
        name = " ".join(_arg(arguments, "name").split())
        if not name:
            return text("Give a name, acronym or alias to search for.", error=True)
        orgs, source = sources.find(name)
        listed = "; ".join(_org_summary(o) for o in orgs) or "none"
        return found(
            [o.document() for o in orgs],
            f"ROR, {source}: {len(orgs)} active organisation(s) named {name!r}: {listed}.",
        )

    return Registry(
        "ror",
        (GET_ORGANISATION, SEARCH_ORGANISATIONS),
        {"get_organisation": get_organisation, "search_organisations": search_organisations},
    )

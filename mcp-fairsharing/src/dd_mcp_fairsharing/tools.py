"""The tools the FAIRsharing server offers, and how a call is answered.

Both tools are read-only and answer `structuredContent` `{"records": [...]}` valid against the
tool's `outputSchema`, with a one-line summary as text: a found record, none when FAIRsharing has
no such record (an empty list, because an MCP client refuses a tool with an output schema that
answers without structured content), or `isError` when the input is invalid, the registry cannot
be asked, or search is called on a server with no FAIRsharing account.

The schemas are written out, not generated, because a client pins each tool's name, description
and schemas (the Data Director's gateway hashes them). Each record is identified at its top level
by `id`, and holds no integers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mcp_types import CallToolResult, TextContent, Tool

from dd_mcp_fairsharing.client import MAX_LIMIT, Fairsharing, NoAccountError, record_id
from dd_mcp_fairsharing.http import UnavailableError
from dd_mcp_fairsharing.records import Record

_TEXT = {"type": "string"}
_OPTIONAL_TEXT = {"type": ["string", "null"]}
_TEXTS = {"type": "array", "items": _TEXT}

RECORD = {
    "type": "object",
    "properties": {
        "id": _TEXT,
        "doi": _OPTIONAL_TEXT,
        "name": _TEXT,
        "abbreviation": _OPTIONAL_TEXT,
        "registry": _OPTIONAL_TEXT,
        "record_type": _OPTIONAL_TEXT,
        "status": _OPTIONAL_TEXT,
        "description": _OPTIONAL_TEXT,
        "homepage": _OPTIONAL_TEXT,
        "subjects": _TEXTS,
        "domains": _TEXTS,
        "url": _TEXT,
        "licence": _TEXT,
    },
    "required": [
        "id",
        "doi",
        "name",
        "abbreviation",
        "registry",
        "record_type",
        "status",
        "description",
        "homepage",
        "subjects",
        "domains",
        "url",
        "licence",
    ],
    "additionalProperties": False,
}


def _records(*, at_most_one: bool) -> dict[str, Any]:
    items: dict[str, Any] = {"type": "array", "items": RECORD}
    if at_most_one:
        items["maxItems"] = 1
    return {
        "type": "object",
        "properties": {"records": items},
        "required": ["records"],
        "additionalProperties": False,
    }


GET_RECORD = Tool(
    name="get_record",
    description=(
        "The FAIRsharing record for an identifier: name, abbreviation, registry, record type, "
        "status, description, homepage, subjects and domains. No records if FAIRsharing has no "
        "such record. Needs no account."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": (
                    "A FAIRsharing identifier (FAIRsharing.xxxxx), its DOI (10.25504/...), a "
                    "fairsharing.org URL, or a numeric record id."
                ),
            }
        },
        "required": ["id"],
        "additionalProperties": False,
    },
    output_schema=_records(at_most_one=True),
)

SEARCH_RECORDS = Tool(
    name="search_records",
    description=(
        "FAIRsharing records matching some words, in FAIRsharing's relevance order, optionally of "
        f"one record type. At most {MAX_LIMIT}. Fails if the server has no FAIRsharing account."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Words to search for."},
            "record_type": {
                "type": "string",
                "description": (
                    "Restrict to one FAIRsharing record type, such as terminology_artefact, "
                    "model_and_format, identifier_schema, reporting_guideline, repository."
                ),
            },
            "limit": {
                "type": "integer",
                "description": f"How many records to return, 1 to {MAX_LIMIT} (default 10).",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    output_schema=_records(at_most_one=False),
)


def found(records: list[dict[str, Any]], summary: str) -> CallToolResult:
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
        except NoAccountError as exc:
            return text(f"{exc}. Use get_record with an identifier instead.", error=True)
        except UnavailableError as exc:
            return text(f"{exc}. Try again later.", error=True)


def _arg(arguments: dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    return value if isinstance(value, str) else ""


def _summary(record: Record) -> str:
    return f"{record.id} ({record.record_type or 'record'}): {record.name}"


def fairsharing_registry(client: Fairsharing) -> Registry:
    """The `fairsharing` server."""

    def get_record(arguments: dict[str, Any]) -> CallToolResult:
        ident = record_id(_arg(arguments, "id"))
        if ident is None:
            return text(
                "Not a FAIRsharing identifier: give FAIRsharing.xxxxx, its DOI, a "
                "fairsharing.org URL or a numeric id.",
                error=True,
            )
        record = client.get(ident)
        if record is None:
            return found([], f"FAIRsharing has no record {ident}.")
        return found([record.document()], f"FAIRsharing: {_summary(record)}.")

    def search_records(arguments: dict[str, Any]) -> CallToolResult:
        query = " ".join(_arg(arguments, "query").split())
        if not query:
            return text("Give some words to search for.", error=True)
        raw_limit = arguments.get("limit", 10)
        if isinstance(raw_limit, bool) or not isinstance(raw_limit, int) or raw_limit < 1:
            return text(f"limit must be a whole number from 1 to {MAX_LIMIT}.", error=True)
        limit = raw_limit
        record_type = _arg(arguments, "record_type").strip() or None
        records = client.search(query, record_type, limit)
        listed = "; ".join(_summary(r) for r in records) or "none"
        return found(
            [r.document() for r in records],
            f"FAIRsharing: {len(records)} record(s) for {query!r}: {listed}.",
        )

    return Registry(
        "fairsharing",
        (GET_RECORD, SEARCH_RECORDS),
        {"get_record": get_record, "search_records": search_records},
    )

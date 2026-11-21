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


def _answer(message: str, records: list[dict[str, Any]] | None = None) -> CallToolResult:
    """`message` with `records` (possibly none) as structured content, or, with no list, as an
    error."""
    return CallToolResult(
        content=[TextContent(type="text", text=message)],
        structured_content=None if records is None else {"records": records},
        is_error=records is None,
    )


class Tools:
    """The FAIRsharing server's tools, and how each call is answered."""

    name = "fairsharing"

    def __init__(self, client: Fairsharing) -> None:
        self.client = client
        self.listed = (GET_RECORD, SEARCH_RECORDS)

    def call(self, tool: str, arguments: dict[str, Any]) -> CallToolResult:
        handler = {"get_record": self._get, "search_records": self._search}.get(tool)
        if handler is None:
            return _answer(f"fairsharing has no tool {tool!r}")
        try:
            return handler(arguments)
        except NoAccountError as exc:
            return _answer(f"{exc}. Use get_record with an identifier instead.")
        except UnavailableError as exc:
            return _answer(f"{exc}. Try again later.")

    def _get(self, arguments: dict[str, Any]) -> CallToolResult:
        given = arguments.get("id")
        ident = record_id(given) if isinstance(given, str) else None
        if ident is None:
            return _answer(
                "Not a FAIRsharing identifier: give FAIRsharing.xxxxx, its DOI, a fairsharing.org "
                "URL or a numeric id."
            )
        record = self.client.get(ident)
        if record is None:
            return _answer(f"FAIRsharing has no record {ident}.", [])
        return _answer(f"FAIRsharing: {_summary(record)}.", [record.document()])

    def _search(self, arguments: dict[str, Any]) -> CallToolResult:
        words = " ".join(str(arguments.get("query") or "").split())
        limit = arguments.get("limit", 10)
        if not words:
            return _answer("Give some words to search for.")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            return _answer(f"limit must be a whole number from 1 to {MAX_LIMIT}.")
        kind = str(arguments.get("record_type") or "").strip() or None
        found = self.client.search(words, kind, limit)
        listed = "; ".join(_summary(r) for r in found) or "none"
        message = f"FAIRsharing: {len(found)} record(s) for {words!r}: {listed}."
        return _answer(message, [r.document() for r in found])


def _summary(record: Record) -> str:
    return f"{record.id} ({record.record_type or 'record'}): {record.name}"

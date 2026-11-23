"""The tools the DOAJ server offers, and how a call is answered.

Both are read-only and answer `structuredContent` `{"records": [...]}` valid against their
`outputSchema`, with a one-line summary as text:

- `get_journal`: the journal with an ISSN, or no records when DOAJ does not list it;
- `search_journals`: the journals whose title matches, in DOAJ's order.

Input that cannot be used, or DOAJ not answering, is `isError`, with no structured content. The
schemas are written out, not generated, because a client pins each tool's name, description and
schemas. Each record is identified at its top level by `id`, DOAJ's own identifier.
"""

from __future__ import annotations

from typing import Any, Protocol

from mcp_types import CallToolResult, TextContent, Tool

from dd_mcp_doaj.journals import SEARCH_ROWS, Doaj, DoajUnavailableError, normal_issn

_TEXT = {"type": "string"}
_MAYBE_TEXT = {"type": ["string", "null"]}
_MAYBE_FLAG = {"type": ["boolean", "null"]}
_TEXTS = {"type": "array", "items": _TEXT}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


RECORD = _object(
    {
        "id": _TEXT,
        "url": _TEXT,
        "title": _TEXT,
        "alternative_title": _MAYBE_TEXT,
        "eissn": _MAYBE_TEXT,
        "pissn": _MAYBE_TEXT,
        "publisher": _MAYBE_TEXT,
        "publisher_country": _MAYBE_TEXT,
        "licences": {"type": "array", "items": _object({"type": _TEXT, "url": _TEXT})},
        "author_retains_copyright": _MAYBE_FLAG,
        "copyright_url": _MAYBE_TEXT,
        "deposit_policy": _object(
            {"has_policy": _MAYBE_FLAG, "services": _TEXTS, "url": _MAYBE_TEXT}
        ),
        "preservation": _object({"has_preservation": _MAYBE_FLAG, "services": _TEXTS}),
        "apc": _object({"has_apc": _MAYBE_FLAG, "highest": _TEXTS, "url": _MAYBE_TEXT}),
        "has_waiver": _MAYBE_FLAG,
        "oa_start": _MAYBE_TEXT,
        "pages": {"type": "object", "additionalProperties": _TEXT},
        "subjects": _TEXTS,
        "last_updated": _MAYBE_TEXT,
    }
)


def _output(most: int) -> dict[str, Any]:
    return _object({"records": {"type": "array", "items": RECORD, "maxItems": most}})


GET_JOURNAL = Tool(
    name="get_journal",
    description=(
        "The Directory of Open Access Journals' record of the journal with an ISSN, print or "
        "electronic: its licences, whether authors keep copyright, its deposit (self-archiving) "
        "policy, preservation services, charges, publisher and the pages that state its terms. "
        "No records if DOAJ does not list it; DOAJ lists open access journals only."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "issn": {
                "type": "string",
                "pattern": r"^\d{4}-?\d{3}[\dXx]$",
                "description": "An ISSN, such as 1932-6203.",
            }
        },
        "required": ["issn"],
        "additionalProperties": False,
    },
    output_schema=_output(1),
)

SEARCH_JOURNALS = Tool(
    name="search_journals",
    description=(
        "Search the Directory of Open Access Journals by journal title. Answers each journal's "
        "record of its open access terms, as get_journal does, in DOAJ's order. DOAJ lists open "
        "access journals only, so a journal not found may still exist."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "minLength": 2, "maxLength": 300},
        },
        "required": ["title"],
        "additionalProperties": False,
    },
    output_schema=_output(SEARCH_ROWS),
)


class Journals(Protocol):
    """What the tools ask of DOAJ (`journals.Doaj`)."""

    def by_issn(self, issn: str) -> dict[str, Any] | None: ...

    def search(self, title: str, rows: int = ...) -> list[dict[str, Any]]: ...


def _error(message: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=message)], is_error=True)


def _found(message: str, records: list[dict[str, Any]]) -> CallToolResult:
    text = TextContent(type="text", text=message)
    return CallToolResult(content=[text], structured_content={"records": records})


class Tools:
    """The DOAJ server's tools, and how each call is answered."""

    name = "doaj"

    def __init__(self, journals: Journals | None = None) -> None:
        self.journals: Journals = journals or Doaj()
        self.listed = (GET_JOURNAL, SEARCH_JOURNALS)

    def call(self, tool: str, arguments: dict[str, Any]) -> CallToolResult:
        try:
            if tool == GET_JOURNAL.name:
                return self._get(arguments.get("issn"))
            if tool == SEARCH_JOURNALS.name:
                return self._search(arguments.get("title"))
        except DoajUnavailableError as exc:
            return _error(f"DOAJ could not be asked: {exc}.")
        return _error(f"doaj has no tool {tool!r}")

    def _get(self, given: Any) -> CallToolResult:
        issn = normal_issn(given) if isinstance(given, str) else None
        if issn is None:
            return _error("Give an ISSN, such as 1932-6203.")
        found = self.journals.by_issn(issn)
        if found is None:
            return _found(f"DOAJ lists no journal with ISSN {issn}.", [])
        return _found(f"DOAJ: {found['title']}, ISSN {issn}.", [found])

    def _search(self, given: Any) -> CallToolResult:
        if not isinstance(given, str) or len(given.strip()) < 2:
            return _error("Give a journal title of at least two characters.")
        found = self.journals.search(given.strip())[:SEARCH_ROWS]
        titles = "; ".join(r["title"] for r in found) or "none"
        return _found(f"DOAJ journals titled {given.strip()!r}: {titles}.", found)

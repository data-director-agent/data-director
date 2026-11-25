"""The tools the Open Policy Finder server offers, and how a call is answered.

All are read-only and answer `structuredContent` `{"records": [...]}` valid against their
`outputSchema`, with a one-line summary as text:

- `search_records`: the records of one item type (a journal, a publisher or a funder) whose name
  has the words given, in Open Policy Finder's order;
- `get_record`: the record with an Open Policy Finder identifier, or, for a journal, an ISSN;
- `get_journal_by_issn`: the journal with an ISSN, with the identifiers of its publishers.

No record found is an empty list. Input that cannot be used, Open Policy Finder not answering, or
no API key is `isError`, with no structured content. The schemas are written out, not generated,
because a client pins each tool's name, description and schemas.
"""

from __future__ import annotations

from typing import Any, Protocol

from mcp_types import CallToolResult, TextContent, Tool

from dd_mcp_opf.client import (
    ITEM_TYPES,
    KEY_NAME,
    SEARCH_LIMIT,
    OpfUnavailableError,
    normal_issn,
)

_TEXT = {"type": "string"}
_MAYBE_TEXT = {"type": ["string", "null"]}
_TEXTS = {"type": "array", "items": _TEXT}
_ANY_LIST = {"type": "array", "items": {}}
_ITEM_TYPE = {"type": "string", "enum": list(ITEM_TYPES)}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


RECORD = _object(
    {
        "item_type": _ITEM_TYPE,
        "id": _TEXT,
        "page": _TEXT,
        "names": _TEXTS,
        "acronyms": _TEXTS,
        "country": _MAYBE_TEXT,
        "url": _MAYBE_TEXT,
        "issns": _TEXTS,
        "publishers": {
            "type": "array",
            "items": _object({"id": _TEXT, "name": _MAYBE_TEXT, "relationship": _MAYBE_TEXT}),
        },
        "identifiers": _ANY_LIST,
        "policies": _ANY_LIST,
    }
)


def _output(most: int) -> dict[str, Any]:
    return _object({"records": {"type": "array", "items": RECORD, "maxItems": most}})


_LICENCE = (
    "The data is Jisc's, under CC BY-NC-ND 4.0 and for non-commercial use; it is read live and "
    "not kept."
)

SEARCH_RECORDS = Tool(
    name="search_records",
    description=(
        "Search Jisc Open Policy Finder, which holds open access policies, for journals "
        "(publication), publishers or funders by name. A funder's record says what it requires "
        "of its outputs, including data archiving; a journal's or publisher's says where a "
        "version of an article may be deposited, after what embargo and under which licence. "
        "A single word in capitals is looked for among acronyms. Answers the records whose names "
        "contain the words given, so keep only those that name the one meant. " + _LICENCE
    ),
    input_schema={
        "type": "object",
        "properties": {
            "item_type": _ITEM_TYPE,
            "text": {"type": "string", "minLength": 2, "maxLength": 300},
        },
        "required": ["item_type", "text"],
        "additionalProperties": False,
    },
    output_schema=_output(SEARCH_LIMIT),
)

GET_RECORD = Tool(
    name="get_record",
    description=(
        "The Jisc Open Policy Finder record of one journal (publication), publisher or funder, "
        "by its Open Policy Finder identifier or, for a journal, its ISSN. No records if there "
        "is none. " + _LICENCE
    ),
    input_schema={
        "type": "object",
        "properties": {
            "item_type": _ITEM_TYPE,
            "identifier": {"type": "string", "minLength": 1, "maxLength": 50},
        },
        "required": ["item_type", "identifier"],
        "additionalProperties": False,
    },
    output_schema=_output(1),
)

GET_JOURNAL_BY_ISSN = Tool(
    name="get_journal_by_issn",
    description=(
        "The Jisc Open Policy Finder record of the journal with an ISSN, print or electronic: "
        "its publishers' identifiers (read each with get_record) and the policies it states. "
        "No records if Open Policy Finder does not list it. " + _LICENCE
    ),
    input_schema={
        "type": "object",
        "properties": {
            "issn": {
                "type": "string",
                "pattern": r"^\d{4}-?\d{3}[\dXx]$",
                "description": "An ISSN, such as 0048-9697.",
            }
        },
        "required": ["issn"],
        "additionalProperties": False,
    },
    output_schema=_output(1),
)


class Records(Protocol):
    """What the tools ask of Open Policy Finder (`client.OpenPolicyFinder`)."""

    def search(self, item_type: Any, text: str, limit: int = ...) -> list[dict[str, Any]]: ...

    def fetch(self, item_type: Any, identifier: str) -> dict[str, Any] | None: ...


def _say(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=message)]


def _error(message: str) -> CallToolResult:
    return CallToolResult(content=_say(message), is_error=True)


def _found(message: str, records: list[dict[str, Any]]) -> CallToolResult:
    return CallToolResult(content=_say(message), structured_content={"records": records})


def _label(record: dict[str, Any]) -> str:
    names = record["names"]
    return str(names[0]) if names else f"{record['item_type']} {record['id']}"


class Tools:
    """The Open Policy Finder server's tools, and how each call is answered. With no `records`
    (no API key), each call is an error that says so."""

    name = "opf"

    def __init__(self, records: Records | None = None) -> None:
        self.records = records
        self.listed = (SEARCH_RECORDS, GET_RECORD, GET_JOURNAL_BY_ISSN)

    def call(self, tool: str, arguments: dict[str, Any]) -> CallToolResult:
        if tool not in {t.name for t in self.listed}:
            return _error(f"opf has no tool {tool!r}")
        if self.records is None:
            return _error(f"Open Policy Finder needs an API key: set {KEY_NAME} on the server.")
        try:
            if tool == SEARCH_RECORDS.name:
                return self._search(arguments.get("item_type"), arguments.get("text"))
            if tool == GET_RECORD.name:
                return self._get(arguments.get("item_type"), arguments.get("identifier"))
            return self._journal(arguments.get("issn"))
        except OpfUnavailableError as exc:
            return _error(f"Open Policy Finder could not be asked: {exc}.")

    def _search(self, item_type: Any, text: Any) -> CallToolResult:
        if item_type not in ITEM_TYPES:
            return _error("Give an item_type: publication, publisher or funder.")
        if self.records is None or not isinstance(text, str) or len(text.strip()) < 2:
            return _error("Give a name of at least two characters.")
        found = self.records.search(item_type, text.strip())[:SEARCH_LIMIT]
        names = "; ".join(_label(r) for r in found) or "none"
        return _found(
            f"Open Policy Finder {item_type} records for {text.strip()!r}: {names}.", found
        )

    def _get(self, item_type: Any, identifier: Any) -> CallToolResult:
        if item_type not in ITEM_TYPES:
            return _error("Give an item_type: publication, publisher or funder.")
        if self.records is None or not isinstance(identifier, str) or not identifier.strip():
            return _error("Give an identifier.")
        found = self.records.fetch(item_type, identifier.strip())
        if found is None:
            return _found(f"Open Policy Finder has no {item_type} {identifier.strip()!r}.", [])
        return _found(f"Open Policy Finder: {_label(found)}.", [found])

    def _journal(self, given: Any) -> CallToolResult:
        issn = normal_issn(given) if isinstance(given, str) else None
        if self.records is None or issn is None:
            return _error("Give an ISSN, such as 0048-9697.")
        found = self.records.fetch("publication", issn)
        if found is None:
            return _found(f"Open Policy Finder lists no journal with ISSN {issn}.", [])
        return _found(f"Open Policy Finder: {_label(found)}, ISSN {issn}.", [found])

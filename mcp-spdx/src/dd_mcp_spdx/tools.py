"""The tool the SPDX server offers, and how a call is answered.

`get_licence` is read-only and answers `structuredContent` `{"records": [...]}` valid against its
`outputSchema`, with a one-line summary as text: the licence's record, none when the pinned
release has no such licence (an empty list, because an MCP client refuses a tool with an output
schema that answers without structured content), or `isError` when the input is not an
identifier.

The schema is written out, not generated, because a client pins each tool's name, description and
schemas (the Data Director's gateway hashes them). Each record is identified at its top level by
`licenseId`, SPDX's own field name, and holds no integers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp_types import CallToolResult, TextContent, Tool

from dd_mcp_spdx.licences import Release, licence, release

_TEXT = {"type": "string"}

RECORD = {
    "type": "object",
    "properties": {
        "licenseId": _TEXT,
        "name": _TEXT,
        "reference": _TEXT,
        "isOsiApproved": {"type": "boolean"},
        "isFsfLibre": {"type": ["boolean", "null"]},
        "isDeprecatedLicenseId": {"type": "boolean"},
        "seeAlso": {"type": "array", "items": _TEXT},
    },
    "required": [
        "licenseId",
        "name",
        "reference",
        "isOsiApproved",
        "isFsfLibre",
        "isDeprecatedLicenseId",
        "seeAlso",
    ],
    "additionalProperties": False,
}

GET_LICENCE = Tool(
    name="get_licence",
    description=(
        "The SPDX licence list's record for a licence identifier, such as CC-BY-4.0: its name, "
        "SPDX page, whether OSI approves it and FSF calls it free, whether the identifier is "
        "deprecated, and the URLs of its text. No records if the pinned release has no such "
        "licence. Identifiers match without regard to case."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "An SPDX licence identifier, such as MIT."}
        },
        "required": ["id"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {"records": {"type": "array", "items": RECORD, "maxItems": 1}},
        "required": ["records"],
        "additionalProperties": False,
    },
)


def _error(message: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=message)], is_error=True)


def _found(message: str, *records: dict[str, Any]) -> CallToolResult:
    """`message`, with `records` (none for a miss) as the structured content."""
    text = TextContent(type="text", text=message)
    return CallToolResult(content=[text], structured_content={"records": list(records)})


class Tools:
    """The SPDX server's tool over one release, and how each call is answered."""

    name = "spdx"

    def __init__(
        self,
        lookup: Callable[[str], dict[str, Any] | None] = licence,
        pinned: Release | None = None,
    ) -> None:
        self.lookup = lookup
        self.release = pinned or release()
        self.listed = (GET_LICENCE,)

    def call(self, tool: str, arguments: dict[str, Any]) -> CallToolResult:
        if tool != GET_LICENCE.name:
            return _error(f"spdx has no tool {tool!r}")
        given = arguments.get("id")
        if not isinstance(given, str) or not given.strip():
            return _error("Give an SPDX licence identifier, such as CC-BY-4.0.")
        found = self.lookup(given)
        where = f"SPDX licence list {self.release.version}"
        if found is None:
            return _found(f"The {where} has no licence {given.strip()!r}.")
        deprecated = " (deprecated identifier)" if found["isDeprecatedLicenseId"] else ""
        return _found(f"{where}: {found['licenseId']}, {found['name']}{deprecated}.", found)

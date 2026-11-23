"""The tools the subjects server offers, and how a call is answered.

Both are read-only and answer `structuredContent` `{"records": [...]}` valid against their
`outputSchema`, with a one-line summary as text:

- `list_terms`: one record, the scheme with every field in it, for a client to choose from;
- `get_term`: one record, one field of a scheme by its code, for a client to cite.

A scheme is named by its identifier (`anzsrc-for`) or by a name a repository writes in a
DataCite `subjectScheme` (`ANZSRC Fields of Research`), matched without regard to case. An
unknown scheme or code answers no records; input that names neither is `isError`.

Every record is identified at its top level by `id`: the scheme's identifier for a scheme, and
`<scheme>:<code>` for a field, so a client that records each by `id` never gives two records one
identifier. The schemas are written out, not generated, because a client pins each tool's name,
description and schemas (the Data Director's gateway hashes them). Records hold no integers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mcp_types import CallToolResult, TextContent, Tool

from dd_subjects import SCHEMES, Scheme, Term, scheme

_TEXT = {"type": "string"}
_PARENT = {"type": ["string", "null"]}

# The names a repository writes for a scheme in a DataCite `subjectScheme`, beside its own name.
ALSO_KNOWN_AS: Mapping[str, tuple[str, ...]] = {
    "anzsrc-for": (
        "ANZSRC Fields of Research",
        "ANZSRC FoR",
        "ANZSRC 2020 Fields of Research",
        "Fields of Research",
    ),
    "oecd-fos": (
        "OECD Fields of Science and Technology",
        "OECD Fields of Research and Development",
        "Fields of Science and Technology",
        "OECD FOS",
    ),
}

_SOURCE = {
    "scheme_name": _TEXT,
    "version": _TEXT,
    "source": _TEXT,
    "licence": _TEXT,
    "attribution": _TEXT,
}
TERM = {
    "type": "object",
    "properties": {
        "id": _TEXT,
        "scheme": _TEXT,
        "code": _TEXT,
        "label": _TEXT,
        "parent": _PARENT,
        **_SOURCE,
    },
    "required": ["id", "scheme", "code", "label", "parent", *_SOURCE],
    "additionalProperties": False,
}
SCHEME = {
    "type": "object",
    "properties": {
        "id": _TEXT,
        "also_known_as": {"type": "array", "items": _TEXT},
        "terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"code": _TEXT, "label": _TEXT, "parent": _PARENT},
                "required": ["code", "label", "parent"],
                "additionalProperties": False,
            },
        },
        **_SOURCE,
    },
    "required": ["id", "also_known_as", "terms", *_SOURCE],
    "additionalProperties": False,
}
_SCHEME_ARG = {
    "type": "string",
    "description": (
        "A scheme's identifier (anzsrc-for, oecd-fos) or a name a repository gives it, such as "
        "ANZSRC Fields of Research."
    ),
}


def _answers(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"records": {"type": "array", "items": record, "maxItems": 1}},
        "required": ["records"],
        "additionalProperties": False,
    }


LIST_TERMS = Tool(
    name="list_terms",
    description=(
        "A subject classification with every field in it, each with its code, its label as "
        "published and the code of the field it is under: the ANZSRC 2020 Fields of Research "
        "(divisions and groups) or the OECD Fields of Research and Development. Also gives the "
        "scheme's version, source, licence and attribution. No records if no scheme has that "
        "name."
    ),
    input_schema={
        "type": "object",
        "properties": {"scheme": _SCHEME_ARG},
        "required": ["scheme"],
        "additionalProperties": False,
    },
    output_schema=_answers(SCHEME),
)

GET_TERM = Tool(
    name="get_term",
    description=(
        "One field of a subject classification by its code, such as 4106 in the ANZSRC Fields "
        "of Research: its label as published, the code of the field it is under, and the "
        "scheme's version, source, licence and attribution. No records if the scheme has no "
        "such code."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "scheme": _SCHEME_ARG,
            "code": {"type": "string", "description": "The field's code, such as 4106."},
        },
        "required": ["scheme", "code"],
        "additionalProperties": False,
    },
    output_schema=_answers(TERM),
)


def scheme_id(name: str) -> str | None:
    """The identifier of the scheme `name` names, by identifier, name or another name it is
    known by, without regard to case; None if no scheme has that name."""
    wanted = " ".join(name.split()).casefold()
    for known in SCHEMES:
        names = (known, scheme(known).name, *ALSO_KNOWN_AS.get(known, ()))
        if wanted in {n.casefold() for n in names}:
            return known
    return None


def _source(found: Scheme) -> dict[str, str]:
    return {
        "scheme_name": found.name,
        "version": found.version,
        "source": found.source,
        "licence": found.licence,
        "attribution": found.attribution,
    }


def scheme_record(found: Scheme) -> dict[str, Any]:
    """`list_terms`' record for a scheme."""
    return {
        "id": found.id,
        "also_known_as": list(ALSO_KNOWN_AS.get(found.id, ())),
        "terms": [{"code": t.code, "label": t.label, "parent": t.parent} for t in found.terms],
        **_source(found),
    }


def term_record(found: Scheme, term: Term) -> dict[str, Any]:
    """`get_term`'s record for one field of a scheme."""
    return {
        "id": f"{found.id}:{term.code}",
        "scheme": found.id,
        "code": term.code,
        "label": term.label,
        "parent": term.parent,
        **_source(found),
    }


def _answer(message: str, *records: dict[str, Any], error: bool = False) -> CallToolResult:
    """`message` as text, and unless the call was in `error`, `records` (none for a miss) as the
    structured content, since a client refuses a tool with an output schema that answers
    without one."""
    return CallToolResult(
        content=[TextContent(type="text", text=message)],
        structured_content=None if error else {"records": list(records)},
        is_error=error,
    )


def _given(arguments: Mapping[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


class Tools:
    """The subjects server's tools over the packaged schemes, and how each call is answered."""

    name = "subjects"
    listed = (LIST_TERMS, GET_TERM)

    def call(self, tool: str, arguments: dict[str, Any]) -> CallToolResult:
        if tool not in {LIST_TERMS.name, GET_TERM.name}:
            return _answer(f"subjects has no tool {tool!r}", error=True)
        named = _given(arguments, "scheme")
        if named is None:
            return _answer(f"Name a scheme: {', '.join(SCHEMES)}.", error=True)
        known = scheme_id(named)
        if known is None:
            return _answer(
                f"No subject scheme is called {named!r}; the schemes are {', '.join(SCHEMES)}."
            )
        found = scheme(known)
        if tool == LIST_TERMS.name:
            return _answer(
                f"{found.name}, {found.version}: {len(found.terms)} fields.", scheme_record(found)
            )
        return _term(found, _given(arguments, "code"))


def _term(found: Scheme, code: str | None) -> CallToolResult:
    """`get_term`'s answer for `code` in `found`."""
    if code is None:
        return _answer(
            f"Give the code of a field of {found.name}, such as {found.terms[1].code}.", error=True
        )
    term = next((t for t in found.terms if t.code == code), None)
    if term is None:
        return _answer(f"{found.name} has no field {code!r}.")
    return _answer(f"{found.name}: {term.code} {term.label}.", term_record(found, term))

"""A metadata record, as the fields the FAIR Assessor checks.

The Metadata Librarian drafts a project's metadata record, and a published record is given in the
same form. The record is read with its standard's definition (`dd_metadata_records`), DataCite's
unless another is named, and the fields are taken from the pivot terms the definition gives its
properties (docs/specs/metadata-standards.md), so that no property of any standard is named here.
A value the researcher has still to give is no value, so a draft with gaps reads as a record with
those fields absent.

This module speaks no Data Director contract and imports nothing from `dd_sdk`.
"""

from __future__ import annotations

from functools import cache
from typing import Any, Final

from dd_metadata_records import RecordError, Standards, discover

# The standard a record is read in when none is named: the one the Metadata Librarian drafts in
# and DataCite's REST API returns.
DATACITE: Final = "http://datacite.org/schema/kernel-4"
MEDIA_TYPE: Final = "application/json"
SCHEMA: Final = "http://schema.org/"


class NotDataCiteError(ValueError):
    """The text is not a record in the standard and serialisation it is read in."""


@cache
def _standards() -> Standards:
    return discover()


def fields(text: str, conforms_to: str = DATACITE, media_type: str = MEDIA_TYPE) -> dict[str, Any]:
    """The record's identifier, title, description, licence, keywords, creators and their
    identifiers, formats and related identifiers, by the names of `PublishedRecord`'s fields.
    A field the record does not give is absent, or an empty list.

    Raises `NotDataCiteError` for text that is not a record in a standard and serialisation a
    registered definition covers."""
    standard = _standards().covering(conforms_to, media_type)
    if standard is None:
        raise NotDataCiteError(f"no registered definition covers {conforms_to} as {media_type}")
    try:
        pivot = standard.read(text, media_type).pivot()
    except RecordError as exc:
        raise NotDataCiteError(f"the text {str(exc).removeprefix('it ')}") from None
    creators = pivot.get(SCHEMA + "creator", ())
    licences = [
        given
        for node in pivot.get(SCHEMA + "license", ())
        if (given := next(iter(node.part(SCHEMA + "identifier")), node.value))
    ]
    return {
        "identifier": _first(pivot.values_of(SCHEMA + "identifier")),
        "title": _first(pivot.values_of(SCHEMA + "name")),
        "description": _first(pivot.values_of(SCHEMA + "description")),
        "licence": _first(licences),
        "keywords": pivot.values_of(SCHEMA + "keywords") + pivot.values_of(SCHEMA + "about"),
        "creators": [node.value for node in creators if node.value is not None],
        "creator_identifiers": [i for node in creators for i in node.part(SCHEMA + "identifier")],
        "formats": pivot.values_of(SCHEMA + "encodingFormat"),
        "related_identifiers": pivot.values_of(SCHEMA + "citation"),
    }


def _first(values: list[str]) -> str | None:
    return values[0] if values else None

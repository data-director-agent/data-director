"""A DataCite record in DataCite's JSON form, as the fields the FAIR Assessor checks.

The Metadata Librarian drafts a project's metadata record in this form: the attributes of the
DataCite REST API, with any value the researcher has still to give left null. `fields` reads the
values that are given and ignores the rest, so a draft with gaps reads as a record with those
fields absent.

This module speaks no Data Director contract and imports nothing from `dd_sdk`, so that it can be
lifted into a neutral library.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any


class NotDataCiteError(ValueError):
    """The text is not a DataCite record in DataCite's JSON form."""


def fields(text: str) -> dict[str, Any]:
    """The record's identifier, title, description, licence, keywords, creators and their
    identifiers, formats and related identifiers, by the names of `PublishedRecord`'s fields.
    A field the record does not give is absent, or an empty list.

    Raises `NotDataCiteError` for text that is not a JSON object."""
    try:
        record = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NotDataCiteError(f"the text is not JSON ({exc.msg})") from exc
    if not isinstance(record, dict):
        raise NotDataCiteError("the text is not a JSON object")
    attributes = record.get("attributes")
    if isinstance(attributes, dict):  # a DataCite REST API response's `data`
        record = attributes
    creators = _objects(record.get("creators"))
    return {
        "identifier": _identifier(record),
        "title": _first(record.get("titles"), "title"),
        "description": _first(record.get("descriptions"), "description"),
        "licence": _licence(record.get("rightsList")),
        "keywords": _values(record.get("subjects"), "subject"),
        "creators": _values(creators, "name"),
        "creator_identifiers": [
            identifier
            for creator in creators
            for identifier in _values(creator.get("nameIdentifiers"), "nameIdentifier")
        ],
        "formats": [f.strip() for f in _list(record.get("formats")) if _text(f)],
        "related_identifiers": _values(record.get("relatedIdentifiers"), "relatedIdentifier"),
    }


def _identifier(record: dict[str, Any]) -> str | None:
    doi = record.get("doi")
    if _text(doi):
        return str(doi).strip()
    for entry in _objects(record.get("identifiers")):
        if _text(entry.get("identifier")):
            return str(entry["identifier"]).strip()
    return None


def _licence(rights_list: Any) -> str | None:
    """The first rights entry's SPDX identifier, else its statement."""
    for entry in _objects(rights_list):
        for key in ("rightsIdentifier", "rights"):
            if _text(entry.get(key)):
                return str(entry[key]).strip()
    return None


def _first(entries: Any, key: str) -> str | None:
    found = _values(entries, key)
    return found[0] if found else None


def _values(entries: Any, key: str) -> list[str]:
    return [str(e[key]).strip() for e in _objects(entries) if _text(e.get(key))]


def _objects(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _list(value: Any) -> Iterable[Any]:
    return value if isinstance(value, list) else ()


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())

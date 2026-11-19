"""Reading a DataCite record in its JSON form, as validation and the package read it
(docs/specs/deposit.md): its attributes, and the values of one requirement field in it."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

# How each DataCite property holds its value, in DataCite's JSON form: the key of the value in
# each entry of a property whose value is a list of objects. It mirrors advisor.metadata's rule
# table; the harness keeps its own, since it imports no agent (docs/specs/system.md).
VALUE_KEYS: Final = {
    "titles": "title",
    "creators": "name",
    "contributors": "name",
    "subjects": "subject",
    "descriptions": "description",
    "dates": "date",
    "rightsList": "rights",
    "fundingReferences": "funderName",
    "relatedIdentifiers": "relatedIdentifier",
    "geoLocations": "geoLocationPlace",
}


def datacite_attributes(text: str) -> dict[str, Any]:
    """The attributes of a DataCite record in its JSON form, as `advisor.metadata` writes it or
    as the DataCite REST API returns it (`{"data": {"attributes": ...}}`). Raises `ValueError` if
    the text is not one."""
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"it is not JSON ({exc.msg} at line {exc.lineno})") from None
    if not isinstance(document, dict):
        raise ValueError("it is not a JSON object")
    data = document.get("data")
    if isinstance(data, dict) and isinstance(data.get("attributes"), dict):
        attributes: dict[str, Any] = data["attributes"]
        return attributes
    return document


def field_values(attributes: Mapping[str, Any], field: Mapping[str, Any]) -> list[str]:
    """The values of one requirement field in a DataCite record: each entry of the property that
    matches the field's qualifier, as text. An absent, empty or null value is no value."""
    head, _, rest = field["property"].partition(".")
    value = attributes.get(head)
    if rest:
        value = value.get(rest) if isinstance(value, dict) else None
        entries = [value]
    else:
        entries = value if isinstance(value, list) else [value]
    qualifier = field.get("qualifier") or {}
    found = []
    for entry in entries:
        if isinstance(entry, dict):
            if any(entry.get(key) != wanted for key, wanted in qualifier.items()):
                continue
            entry = entry.get(VALUE_KEYS.get(head, ""))
        elif qualifier:
            continue
        if isinstance(entry, str | int | float) and str(entry).strip():
            found.append(str(entry).strip())
    return found

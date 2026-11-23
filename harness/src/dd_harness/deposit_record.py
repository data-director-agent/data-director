"""The approved metadata record as the deposit check and the package read it: a DataCite record in
its JSON form, read through the merged requirement set's fields, each value under its field's term
(docs/specs/deposit.md, Validation; docs/specs/metadata-standards.md, The pivot). The root dataset
of the package is described from it. A standard's definition takes the DataCite keys here over in
#1358.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final

from rdflib import Namespace
from rocrate.model import Person
from rocrate.rocrate import ROCrate

from dd_harness.package_crate import creative_work
from dd_sdk.contract.requirements import expand_term

SCHEMA = Namespace("http://schema.org/")
# The root dataset's terms whose value is a person, and those it writes itself, not from a field.
_ROOT_PEOPLE: Final = frozenset({str(SCHEMA.creator), str(SCHEMA.contributor)})
_ROOT_OWN: Final = frozenset({str(SCHEMA.license), str(SCHEMA.datePublished)})
# What the root dataset describes whatever the merged set asks for, read as a field would be: a
# set with no field of the term still gets it. A standard's definition gives these in #1358.
_ROOT_DEFAULTS: Final[tuple[dict[str, Any], ...]] = (
    {"property": "titles", "term": "schema:name"},
    {
        "property": "descriptions",
        "qualifier": {"descriptionType": "Abstract"},
        "term": "schema:description",
    },
    {"property": "subjects", "term": "schema:keywords"},
    {"property": "dates", "qualifier": {"dateType": "Created"}, "term": "schema:dateCreated"},
    {"property": "types.resourceTypeGeneral", "term": "schema:additionalType"},
    {"property": "creators", "term": "schema:creator"},
)
# The root dataset's terms that take one value, RO-Crate's name and description among them: the
# first of the record's.
_ROOT_SINGLE: Final = frozenset(
    str(SCHEMA[term]) for term in ("name", "description", "dateCreated", "additionalType")
)

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


def describe_root(
    crate: ROCrate,
    record: Mapping[str, Any],
    requirements: Mapping[str, Any],
    made_at: datetime,
) -> None:
    """The root dataset's properties, from the approved metadata record read through the merged
    set's fields, as the validation reads it: each field's values under its term, and those of
    `_ROOT_DEFAULTS` the set has no field for. A schema.org term is written by its name, as
    RO-Crate's context has it, and any other by its IRI (docs/specs/metadata-standards.md, The
    pivot)."""
    root = crate.root_dataset
    root["datePublished"] = made_at.date().isoformat()
    attributes: Mapping[str, Any] = {}
    if record.get("document_text"):
        try:
            attributes = datacite_attributes(record["document_text"])
        except ValueError:
            attributes = {}
    fields: list[Mapping[str, Any]] = list(requirements.get("fields") or [])
    asked = {expand_term(field["term"]) for field in fields}
    fields += [field for field in _ROOT_DEFAULTS if expand_term(field["term"]) not in asked]
    for field in fields:
        iri = expand_term(field["term"])
        found = field_values(attributes, field)
        if not found or iri in _ROOT_OWN:
            continue
        key = iri.removeprefix(str(SCHEMA)) if iri.startswith(str(SCHEMA)) else iri
        if iri in _ROOT_PEOPLE:
            people = [
                crate.add(Person(crate, f"#{key}-{n + 1}", properties={"name": name}))
                for n, name in enumerate(found)
            ]
            root[key] = people if len(people) > 1 else people[0]
        elif iri == str(SCHEMA.keywords):
            root[key] = ", ".join(found)
        else:
            root[key] = found if len(found) > 1 and iri not in _ROOT_SINGLE else found[0]
    licences = [
        str(r.get("rightsUri") or r.get("rightsIdentifier") or r.get("rights"))
        for r in attributes.get("rightsList") or []
        if isinstance(r, dict) and (r.get("rightsUri") or r.get("rightsIdentifier"))
    ]
    if licences:
        licence = licences[0]
        if not licence.startswith(("http://", "https://")):
            licence = f"https://spdx.org/licenses/{licence}"
        root["license"] = creative_work(crate, licence, licence)

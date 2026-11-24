"""The approved metadata record as the deposit check and the package read it: a record in any
registered standard, read with its standard's definition, each requirement field's values under
its field's term (docs/specs/deposit.md, Validation; docs/specs/metadata-standards.md, The pivot).
The root dataset of the package is described from it. No property of a standard is named here:
the definition names them.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final

from rdflib import Namespace
from rocrate.model import Person
from rocrate.rocrate import ROCrate

from dd_harness.package_crate import creative_work
from dd_metadata_records import Record
from dd_sdk.contract.requirements import expand_term

SCHEMA = Namespace("http://schema.org/")
# The root dataset's terms whose value is a person, and those it writes itself, not from a field.
_ROOT_PEOPLE: Final = frozenset({str(SCHEMA.creator), str(SCHEMA.contributor)})
_ROOT_OWN: Final = frozenset({str(SCHEMA.license), str(SCHEMA.datePublished)})
# What the root dataset describes whatever the merged set asks for, read from the pivot: a set
# with no field of the term still gets it.
_ROOT_DEFAULTS: Final = tuple(
    str(SCHEMA[term])
    for term in ("name", "description", "keywords", "dateCreated", "additionalType", "creator")
)
# The root dataset's terms that take one value, RO-Crate's name and description among them: the
# first of the record's.
_ROOT_SINGLE: Final = frozenset(
    str(SCHEMA[term]) for term in ("name", "description", "dateCreated", "additionalType")
)


def licences(record: Record) -> list[tuple[str | None, str | None, str | None]]:
    """Each licence the record gives, as its identifier, its URL and its name, any of them None:
    the nodes of the pivot's `schema:license`."""
    return [
        (_first(node.part(str(SCHEMA.identifier))), _first(node.part(str(SCHEMA.url))), node.value)
        for node in record.pivot().get(str(SCHEMA.license), ())
    ]


def _first(values: list[str]) -> str | None:
    return values[0] if values else None


def describe_root(
    crate: ROCrate,
    record: Record | None,
    requirements: Mapping[str, Any],
    made_at: datetime,
) -> None:
    """The root dataset's properties, from the approved metadata record read through the merged
    set's fields, as the validation reads it: each field's values under its term, and the values
    of the pivot under each of `_ROOT_DEFAULTS` the set has no field for. A schema.org term is
    written by its name, as RO-Crate's context has it, and any other by its IRI
    (docs/specs/metadata-standards.md, The pivot)."""
    root = crate.root_dataset
    root["datePublished"] = made_at.date().isoformat()
    if record is None:
        return
    fields: list[Mapping[str, Any]] = list(requirements.get("fields") or [])
    found: dict[str, list[str]] = {}
    for field in fields:
        iri = expand_term(field["term"])
        found.setdefault(iri, record.values(field["property"], field.get("qualifier")))
    pivot = record.pivot()
    for iri in _ROOT_DEFAULTS:
        found.setdefault(iri, pivot.values_of(iri))
    for iri, values in found.items():
        if not values or iri in _ROOT_OWN:
            continue
        key = iri.removeprefix(str(SCHEMA)) if iri.startswith(str(SCHEMA)) else iri
        if iri in _ROOT_PEOPLE:
            people = [
                crate.add(Person(crate, f"#{key}-{n + 1}", properties={"name": name}))
                for n, name in enumerate(values)
            ]
            root[key] = people if len(people) > 1 else people[0]
        elif iri == str(SCHEMA.keywords):
            root[key] = ", ".join(values)
        else:
            root[key] = values if len(values) > 1 and iri not in _ROOT_SINGLE else values[0]
    given = [
        str(url or identifier) for identifier, url, _name in licences(record) if url or identifier
    ]
    if given:
        licence = given[0]
        if not licence.startswith(("http://", "https://")):
            licence = f"https://spdx.org/licenses/{licence}"
        root["license"] = creative_work(crate, licence, licence)

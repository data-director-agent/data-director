"""A requirement set's fields read against their standard's definition
(docs/specs/metadata-standards.md, A requirement set): a field that leaves out its term is given the
one the definition gives its property and qualifier, and a field that names another is refused,
as is a set whose standard no registered definition covers."""

from __future__ import annotations

import json
from typing import Any

from dd_metadata_records import Standards
from dd_sdk.contract.models import RequirementSet
from dd_sdk.contract.requirements import expand_term


def defined_terms(data: dict[str, Any], definitions: Standards) -> dict[str, Any]:
    """A set whose fields leave out their term, with the term its standard's definition gives
    each field's property and qualifier. A field the definition gives no term keeps none, and the
    schema refuses it."""
    fields = data.get("fields")
    standard = definitions.by_uri(data.get("conforms_to"))
    if standard is None or not isinstance(fields, list):
        return data
    filled = []
    for field in fields:
        if (
            isinstance(field, dict)
            and "term" not in field
            and isinstance(field.get("property"), str)
        ):
            term = standard.definition.term(field["property"], field.get("qualifier"))
            field = {**field, "term": term} if term else field
        filled.append(field)
    return {**data, "fields": filled}


def definition_problem(found: RequirementSet, definitions: Standards) -> str | None:
    """Why a set cannot be read through its standard's definition (invariant 11 of
    docs/specs/metadata-standards.md), or None: its standard no registered definition covers, or a
    field names a term other than the one the definition gives its property and qualifier."""
    standard = definitions.by_uri(found.conforms_to)
    if standard is None:
        return (
            f"{found.requirement_set_id!r} follows {found.conforms_to}, which no registered "
            "standard's definition covers (docs/specs/metadata-standards.md)"
        )
    definition = standard.definition
    for field in found.fields:
        given = definition.term(field.property, field.qualifier)
        if given is not None and given != expand_term(field.term):
            qualifier = json.dumps(field.qualifier, sort_keys=True)
            named = field.property if qualifier == "null" else f"{field.property} {qualifier}"
            return (
                f"{found.requirement_set_id!r} reads {named} under {field.term}, but "
                f"{definition.ref} gives it {given}; a field's term is its standard's "
                "(docs/specs/metadata-standards.md)"
            )
    return None

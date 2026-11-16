"""The registered defects: named, deterministic faults applied to a known-good `DraftRequest`.

A case takes a base request and breaks it in one named way, so what the Documentation Editor should
do follows from the defect. As in the standards advisor's registry, a new mutation is a new name,
and a registered name's behaviour never changes: otherwise a baseline recorded against a defect
would silently start measuring something else (docs/specs/evaluation.md, invariant 6).

A defect takes a request document and returns a new one; it never mutates its argument.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Document = dict[str, Any]


@dataclass(frozen=True)
class Defect:
    name: str
    description: str
    apply: Callable[[Document], Document]


def _none(doc: Document) -> Document:
    return doc


def _drop_metadata_record(doc: Document) -> Document:
    doc.pop("metadata_record", None)
    return doc


def _drop_inventory(doc: Document) -> Document:
    doc.pop("inventory", None)
    return doc


def _drop_fields(doc: Document) -> Document:
    for f in (doc.get("inventory") or {}).get("inventory_files", []):
        f.pop("file_fields", None)
    return doc


def _blank_record_title_and_creators(doc: Document) -> Document:
    record = doc.get("metadata_record")
    if record is None:
        return doc
    properties = json.loads(record["document_text"])
    properties["titles"] = [{"title": "  "}]
    properties["creators"] = [{"name": None, "nameType": "Personal"}]
    record["document_text"] = json.dumps(properties, indent=2, ensure_ascii=False)
    return doc


def _record_not_datacite(doc: Document) -> Document:
    record = doc.get("metadata_record")
    if record is not None:
        record["conforms_to"] = "https://schema.org/Dataset"
    return doc


DEFECTS: dict[str, Defect] = {
    d.name: d
    for d in (
        Defect("none", "The base request, unchanged.", _none),
        Defect(
            "drop-metadata-record",
            "The approved metadata record is removed: the README is drafted from the inventory "
            "alone.",
            _drop_metadata_record,
        ),
        Defect(
            "drop-inventory",
            "The file inventory is removed: there is nothing to draft from.",
            _drop_inventory,
        ),
        Defect(
            "drop-fields",
            "Every file's table fields are removed: there is no table for a data dictionary.",
            _drop_fields,
        ),
        Defect(
            "blank-record-title-and-creators",
            "The record's title is blank and its one creator has no name: the README asks for "
            "both.",
            _blank_record_title_and_creators,
        ),
        Defect(
            "record-not-datacite",
            "The record says it conforms to schema.org, not DataCite: the editor does not read it.",
            _record_not_datacite,
        ),
    )
}


def apply_defect(name: str, doc: Document) -> Document:
    """A copy of `doc` with the defect `name` applied. An unknown name raises `KeyError`."""
    return DEFECTS[name].apply(copy.deepcopy(doc))

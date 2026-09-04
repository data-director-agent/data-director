"""Evidence hashing (ADR-0009).

A content hash covers the canonicalised *projection* of the thing a grounding claim rests on,
not an HTTP body. `EvidenceItem.canonicalisation` names which projection was used, so a reader
(or the linter, offline) can recompute the hash from the same source. The names are registered
here; an unknown name is a programmer error, and `contract.validate` rejects an envelope that
cites one.

Three canonicalisations exist:

- `json-sorted-utf8-v1` — the FAIRsharing record projection R3 uses. Name and bytes are
  unchanged from v0 so hashes in stored runs still verify.
- `dd-input-json-v1` — the whole input document of an invocation, as `to_document` emits it.
  What an `input_only` or `none` agent cites: it rests on nothing but what it was given.
- `dd-json-document-v1` — a whole retrieved record, as the source handed it over, with no
  projection. For sources whose records are already small and self-describing.

Adding a field to a projection changes every hash it produces; do it deliberately and register
a new name rather than editing an existing one.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

HASH_ALGORITHM = "sha256"


@dataclass(frozen=True)
class Canonicalisation:
    name: str
    description: str
    apply: Callable[[dict[str, Any]], bytes]


# --- json-sorted-utf8-v1: FAIRsharing record projection --------------------------------------

CANONICALISATION = "json-sorted-utf8-v1"

# The fields an R3 recommendation's grounding rests on.
PROJECTED_FIELDS = (
    "fairsharing_id",
    "doi",
    "name",
    "abbreviation",
    "record_type",
    "status",
    "description",
    "subjects",
    "domains",
)


def _fairsharing_projection(record: dict[str, Any]) -> bytes:
    """Project to PROJECTED_FIELDS, then JSON with sorted keys, no whitespace, UTF-8.

    Lists of labels are sorted so that ordering differences between routes do not change the
    hash. Values are strings, lists of strings or null, so Python's json module is adequate;
    RFC 8785 number canonicalisation is not needed.
    """
    projection: dict[str, Any] = {}
    for key in PROJECTED_FIELDS:
        value = record.get(key)
        if isinstance(value, list):
            value = sorted(str(v) for v in value)
        projection[key] = value
    return _dumps(projection)


# --- dd-input-json-v1: the whole input document ----------------------------------------------

INPUT_CANONICALISATION = "dd-input-json-v1"


def _input_projection(document: dict[str, Any]) -> bytes:
    """The input document as `to_document` emits it: sorted keys, no whitespace, UTF-8.

    Lists are *not* sorted: field order in a DatasetProfile or creator order in a record is
    meaningful, and the document is already free of None values.
    """
    return _dumps(document)


# --- dd-json-document-v1: a whole retrieved record -------------------------------------------

DOCUMENT_CANONICALISATION = "dd-json-document-v1"


def _dumps(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


CANONICALISATIONS: dict[str, Canonicalisation] = {
    c.name: c
    for c in (
        Canonicalisation(
            CANONICALISATION,
            "FAIRsharing record projected to PROJECTED_FIELDS; label lists sorted.",
            _fairsharing_projection,
        ),
        Canonicalisation(
            INPUT_CANONICALISATION,
            "The invocation's whole input document; lists in document order.",
            _input_projection,
        ),
        Canonicalisation(
            DOCUMENT_CANONICALISATION,
            "A whole retrieved record, unprojected; lists in document order.",
            _dumps,
        ),
    )
}


def canonicalise(record: dict[str, Any], canonicalisation: str = CANONICALISATION) -> bytes:
    try:
        return CANONICALISATIONS[canonicalisation].apply(record)
    except KeyError:
        raise ValueError(
            f"unknown canonicalisation {canonicalisation!r}; registered: "
            f"{sorted(CANONICALISATIONS)}"
        ) from None


def content_hash(record: dict[str, Any], canonicalisation: str = CANONICALISATION) -> str:
    return hashlib.sha256(canonicalise(record, canonicalisation)).hexdigest()


def input_hash(input_document: dict[str, Any]) -> str:
    """The `dd-input-json-v1` hash of an invocation's input document."""
    return content_hash(input_document, INPUT_CANONICALISATION)

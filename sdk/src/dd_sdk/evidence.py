"""Evidence hashing (ADR-0009, ADR-0015).

A content hash covers the canonicalised *projection* of the thing a grounding claim rests on,
not an HTTP body. `EvidenceItem.canonicalisation` names which projection was used, and
`EvidenceItem.content` may carry the projection itself (`project`), so a reader or the linter
can recompute the hash from the envelope alone (`verify`). The names are registered
here; an unknown name is a programmer error, and `contract.validate` rejects an envelope that
cites one.

Four canonicalisations exist:

- `json-sorted-utf8-v1` — the FAIRsharing record projection R3 uses. Name and bytes are
  unchanged from v0 so hashes in stored runs still verify.
- `dd-input-json-v1` — the whole input document of an invocation, as `to_document` emits it.
  What an `input_only` or `none` agent cites: it rests on nothing but what it was given.
- `dd-json-document-v1` — a whole retrieved record, as the source handed it over, with no
  projection. For sources whose records are already small and self-describing.
- `dd-envelope-json-v1` — a whole child envelope, as the conductor stored it in
  `runs/<invocation_id>/envelope.json`. What a `delegation` agent cites for a reply it relays
  (ADR-0012).

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
    """A name, a description and a projection. The canonical bytes are always the projection
    dumped as JSON with sorted keys, no whitespace, UTF-8; the projection is what evidence
    `content` holds (ADR-0015)."""

    name: str
    description: str
    project: Callable[[dict[str, Any]], dict[str, Any]]


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


def _fairsharing_projection(record: dict[str, Any]) -> dict[str, Any]:
    """Project to PROJECTED_FIELDS; the bytes are then JSON with sorted keys, no whitespace, UTF-8.

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
    return projection


# --- dd-input-json-v1: the whole input document ----------------------------------------------

INPUT_CANONICALISATION = "dd-input-json-v1"


def _whole(document: dict[str, Any]) -> dict[str, Any]:
    """No projection: the document as given.

    For `dd-input-json-v1`, lists are *not* sorted: field order in a DatasetProfile or creator
    order in a record is meaningful, and the document is already free of None values.
    """
    return document


# --- dd-json-document-v1: a whole retrieved record -------------------------------------------

DOCUMENT_CANONICALISATION = "dd-json-document-v1"


# --- dd-envelope-json-v1: a whole child envelope ---------------------------------------------

ENVELOPE_CANONICALISATION = "dd-envelope-json-v1"


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
            _whole,
        ),
        Canonicalisation(
            DOCUMENT_CANONICALISATION,
            "A whole retrieved record, unprojected; lists in document order.",
            _whole,
        ),
        Canonicalisation(
            ENVELOPE_CANONICALISATION,
            "A whole envelope document as stored; lists in document order.",
            _whole,
        ),
    )
}


def _registered(canonicalisation: str) -> Canonicalisation:
    try:
        return CANONICALISATIONS[canonicalisation]
    except KeyError:
        raise ValueError(
            f"unknown canonicalisation {canonicalisation!r}; registered: "
            f"{sorted(CANONICALISATIONS)}"
        ) from None


def project(record: dict[str, Any], canonicalisation: str = CANONICALISATION) -> dict[str, Any]:
    """What `canonicalisation` hashes of `record`: the value evidence `content` carries.

    Projecting a projection changes nothing, so `canonicalise(project(r)) == canonicalise(r)`.
    """
    return _registered(canonicalisation).project(record)


def canonicalise(record: dict[str, Any], canonicalisation: str = CANONICALISATION) -> bytes:
    return _dumps(project(record, canonicalisation))


def content_hash(record: dict[str, Any], canonicalisation: str = CANONICALISATION) -> str:
    return hashlib.sha256(canonicalise(record, canonicalisation)).hexdigest()


def verify(content: dict[str, Any], canonicalisation: str, expected_hash: str) -> bool:
    """Whether evidence `content` hashes to `expected_hash` (linter rule E1, ADR-0015)."""
    return content_hash(content, canonicalisation) == expected_hash


def input_hash(input_document: dict[str, Any]) -> str:
    """The `dd-input-json-v1` hash of an invocation's input document."""
    return content_hash(input_document, INPUT_CANONICALISATION)


def envelope_hash(envelope_document: dict[str, Any]) -> str:
    """The `dd-envelope-json-v1` hash of an envelope document (ADR-0012)."""
    return content_hash(envelope_document, ENVELOPE_CANONICALISATION)


def resolve(envelope: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any] | None:
    """The evidence `content` a grounding reference identifies, or None if it carries none.

    The reader's side of ADR-0015: a payload names a record only in `grounded_on`, and what it
    names is read from the evidence item with the same `source_id` and `content_hash`.
    """
    for ev in envelope.get("evidence") or []:
        if (ev.get("source_id"), ev.get("content_hash")) == (
            ref.get("source_id"),
            ref.get("content_hash"),
        ):
            content: dict[str, Any] | None = ev.get("content")
            return content
    return None

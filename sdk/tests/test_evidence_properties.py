"""Property tests for evidence canonicalisation (docs/specs/grounding.md, invariants 7 and 9).

Every registered canonicalisation is checked against a reference written out here, independently
of `dd_sdk.evidence`, so a change to the bytes an existing name produces fails a test rather than
relying on review. A new name needs a reference and a pinned digest before these tests pass.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dd_sdk.evidence import CANONICALISATIONS, canonicalise, content_hash, project, verify

# --- The reference: what each name's bytes are, written out from the spec ----------------------


def _reference_dumps(value: Any) -> bytes:
    """JSON with sorted keys, no whitespace, UTF-8 without escapes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


# The FAIRsharing projection's fields, copied rather than imported so that a change there fails.
_FAIRSHARING_FIELDS = (
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


def _reference_fairsharing(record: dict[str, Any]) -> bytes:
    """Each projected field, null when absent; a list's items as strings, sorted."""
    projection = {}
    for key in _FAIRSHARING_FIELDS:
        value = record.get(key)
        projection[key] = sorted(str(v) for v in value) if isinstance(value, list) else value
    return _reference_dumps(projection)


_SPDX_FIELDS = (
    "licenseId",
    "name",
    "isOsiApproved",
    "isFsfLibre",
    "isDeprecatedLicenseId",
    "seeAlso",
)


def _reference_spdx(record: dict[str, Any]) -> bytes:
    """Each projected field, null when absent; `seeAlso` as sorted strings."""
    projection = {}
    for key in _SPDX_FIELDS:
        value = record.get(key)
        projection[key] = sorted(str(v) for v in value) if isinstance(value, list) else value
    return _reference_dumps(projection)


REFERENCE: dict[str, Callable[[dict[str, Any]], bytes]] = {
    "json-sorted-utf8-v1": _reference_fairsharing,
    "dd-input-json-v1": _reference_dumps,
    "dd-json-document-v1": _reference_dumps,
    "dd-envelope-json-v1": _reference_dumps,
    "dd-spdx-licence-v1": _reference_spdx,
}

# A fixed record and the digest each name gives it, as first registered. Never edit a digest:
# register a new name instead (AGENTS.md, "an existing name's bytes never change").
PINNED_RECORD: dict[str, Any] = {
    "fairsharing_id": "FAIRsharing.b44s4",
    "doi": "10.25504/FAIRsharing.b44s4",
    "name": "Data Documentation Initiative",
    "abbreviation": "DDI",
    "record_type": "model_and_format",
    "status": "ready",
    "description": 'Métadonnées pour les sciences sociales — ✓ "quoted" \\ and\nnewline',
    "subjects": ["Social Science", "Demography", "Économie"],
    "domains": ["Survey", "Census"],
    "not_projected": {
        "z": [3, 1, 2],
        "a": None,
        "n": -0.0,
        "big": 12345678901234567890,
        "f": 1.5e-7,
    },
}
WHOLE_DIGEST = "4d54e5014b2b434e99cf9556c7d5b0d777bd6f95e243c6635f8dce58d437f587"
PINNED_DIGEST = {
    "json-sorted-utf8-v1": "4631babea2648877fbfc8e4690e130e204fa837529c3dce00a00416013154c2f",
    "dd-input-json-v1": WHOLE_DIGEST,
    "dd-json-document-v1": WHOLE_DIGEST,
    "dd-envelope-json-v1": WHOLE_DIGEST,
    "dd-spdx-licence-v1": "e4f537e0181c581ba783a133667fb727bcf595beeba7346839efc636def51121",
}
# A name registered later is pinned on a record of its own, so no earlier digest moves.
PINNED_RECORDS: dict[str, dict[str, Any]] = {
    "dd-spdx-licence-v1": {
        "licenseId": "CC-BY-4.0",
        "name": "Creative Commons Attribution 4.0 International",
        "isOsiApproved": False,
        "seeAlso": ["https://creativecommons.org/licenses/by/4.0/legalcode", "https://a.example/"],
        "licenseText": "Not projected.",
    }
}

# --- Generated documents --------------------------------------------------------------------------

# JSON values Python's json module round-trips: no NaN or infinity, string keys.
json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(),
    lambda inner: st.lists(inner, max_size=4) | st.dictionaries(st.text(), inner, max_size=4),
    max_leaves=12,
)
# Documents that mix the FAIRsharing projection's fields with others, so that every name sees
# lists to sort, fields to drop and fields to fill with null.
documents = st.dictionaries(
    st.sampled_from(_FAIRSHARING_FIELDS + _SPDX_FIELDS) | st.text(max_size=8),
    json_values | st.lists(st.text() | st.integers(), max_size=4),
    max_size=8,
)
names = st.sampled_from(sorted(CANONICALISATIONS))


def test_every_registered_canonicalisation_has_a_reference_and_a_pin() -> None:
    assert set(REFERENCE) == set(CANONICALISATIONS)
    assert set(PINNED_DIGEST) == set(CANONICALISATIONS)


@pytest.mark.parametrize("name", sorted(PINNED_DIGEST))
def test_a_registered_canonicalisation_gives_its_pinned_digest(name: str) -> None:
    record = PINNED_RECORDS.get(name, PINNED_RECORD)
    assert content_hash(record, name) == PINNED_DIGEST[name]
    assert hashlib.sha256(REFERENCE[name](record)).hexdigest() == PINNED_DIGEST[name]


@given(document=documents, name=names)
def test_the_bytes_of_a_canonicalisation_are_its_references(
    document: dict[str, Any], name: str
) -> None:
    expected = REFERENCE[name](document)
    assert canonicalise(document, name) == expected
    assert content_hash(document, name) == hashlib.sha256(expected).hexdigest()


@given(document=documents, name=names)
def test_canonicalising_twice_gives_the_bytes_of_canonicalising_once(
    document: dict[str, Any], name: str
) -> None:
    once = canonicalise(document, name)
    assert canonicalise(project(document, name), name) == once
    assert canonicalise(json.loads(once), name) == once


@given(document=documents, name=names)
def test_a_projection_verifies_against_the_hash_of_its_document(
    document: dict[str, Any], name: str
) -> None:
    """E1 recomputes the hash from the evidence `content`, the projection, alone."""
    assert verify(project(document, name), name, content_hash(document, name))


def test_the_spdx_projection_ignores_the_text_and_the_order_of_references() -> None:
    record = PINNED_RECORDS["dd-spdx-licence-v1"]
    reshaped = {
        **record,
        "licenseText": "Other text.",
        "seeAlso": list(reversed(record["seeAlso"])),
    }
    assert content_hash(reshaped, "dd-spdx-licence-v1") == content_hash(
        record, "dd-spdx-licence-v1"
    )
    assert "licenseText" not in project(record, "dd-spdx-licence-v1")

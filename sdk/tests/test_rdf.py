"""A payload read as JSON-LD for its class's SHACL shapes (dd_sdk.contract.rdf), and the shapes a
class carries on the card (docs/specs/contract.md)."""

from __future__ import annotations

import json

import pytest

from dd_sdk.contract.classes import ClassSchema, ClassSchemaError
from dd_sdk.contract.models import Document
from dd_sdk.contract.rdf import payload_jsonld

DOCUMENT = ClassSchema.of(Document)
REF = {"source_id": "input:x", "content_hash": "0" * 64}


def _document(**slots: object) -> dict[str, object]:
    return {
        "schema_class": "Document",
        "document_kind": "readme",
        "media_type": "text/markdown",
        "document_text": "# Survey\n",
        "document_derivation": "model",
        "grounded_on": [REF],
        **slots,
    }


def test_a_core_payload_class_carries_its_shapes_and_context() -> None:
    assert DOCUMENT.shapes is not None
    assert "sh:NodeShape" in DOCUMENT.shapes.shacl
    terms = DOCUMENT.shapes.context["@context"]
    assert {"Document", "GroundingRef", "grounded_on", "document_text"} <= set(terms)
    assert "invocation_id" not in terms  # a keyword alias the class does not use stays out


def test_shapes_on_the_card_are_checked_against_their_digest() -> None:
    entry = json.loads(json.dumps(DOCUMENT.describe()))
    assert ClassSchema.from_description("Document", entry).shapes == DOCUMENT.shapes
    entry["shapes"]["context"]["@vocab"] = "https://example.org/"
    with pytest.raises(ClassSchemaError):
        ClassSchema.from_description("Document", entry)


def test_the_payload_and_its_nested_objects_name_their_classes() -> None:
    doc = payload_jsonld(_document(revises={"document_id": "0" * 8, "version": 2}), DOCUMENT)
    assert doc["@context"] == DOCUMENT.shapes.context["@context"]  # type: ignore[union-attr]
    assert doc["@type"] == "Document"
    assert doc["grounded_on"][0]["@type"] == "GroundingRef"
    assert doc["revises"]["@type"] == "DocumentVersionRef"


def test_an_integer_sent_as_a_double_is_read_as_an_integer() -> None:
    doc = payload_jsonld(_document(revises={"document_id": "0", "version": 2.0}), DOCUMENT)
    assert doc["revises"]["version"] == 2 and isinstance(doc["revises"]["version"], int)


def test_a_class_without_shapes_cannot_be_read_as_json_ld() -> None:
    entry = DOCUMENT.describe()
    del entry["shapes"]
    with pytest.raises(ValueError):
        payload_jsonld(_document(), ClassSchema.from_description("Document", entry))

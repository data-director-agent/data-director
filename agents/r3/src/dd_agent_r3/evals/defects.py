"""The registered defects: named, deterministic faults applied to a known-good dataset profile.

A seeded-defect case takes a base profile and breaks it in one named way, so what R3 should do
follows from the defect and nobody has to hand-label the case. The rule is the one
`dd_sdk.evidence.CANONICALISATIONS` follows: a new mutation is a new name, and a registered
name's behaviour never changes. Otherwise a baseline recorded against a defect would silently
start measuring something else.

A defect takes a profile document and returns a new one; it never mutates its argument.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dd_agent_r3.rank import TEMPORAL_TYPES

Document = dict[str, Any]


@dataclass(frozen=True)
class Defect:
    name: str
    description: str
    apply: Callable[[Document], Document]


def _none(doc: Document) -> Document:
    return doc


def _drop_temporal_fields(doc: Document) -> Document:
    doc["fields"] = [f for f in doc.get("fields", []) if f.get("field_type") not in TEMPORAL_TYPES]
    return doc


def _drop_media_types(doc: Document) -> Document:
    doc.pop("media_types", None)
    return doc


def _drop_themes_keywords(doc: Document) -> Document:
    doc.pop("themes", None)
    doc.pop("keywords", None)
    return doc


def _empty_all(doc: Document) -> Document:
    return {"schema_class": doc["schema_class"]}


# Text about a discipline far from the base profile's. Fields and media types are kept, so the
# format recommendations still apply and only the subject recommendations should change.
OFF_DOMAIN_TEXT: Document = {
    "title": "Marginal annotations in fifteenth-century Welsh poetry manuscripts",
    "description": (
        "Transcriptions and palaeographic notes on marginal annotations found in twelve "
        "fifteenth-century manuscripts of Welsh strict-metre poetry, with the hand, ink and "
        "position of each annotation recorded."
    ),
    "keywords": ["palaeography", "Welsh poetry", "manuscripts", "marginalia"],
    "themes": ["Literature", "History"],
}


def _off_domain(doc: Document) -> Document:
    doc.update(copy.deepcopy(OFF_DOMAIN_TEXT))
    return doc


def _unhelpful_title(doc: Document) -> Document:
    doc["title"] = "Dataset 1"
    return doc


DEFECTS: dict[str, Defect] = {
    d.name: d
    for d in (
        Defect("none", "The base profile, unchanged.", _none),
        Defect(
            "drop-temporal-fields",
            f"Every field whose type is one of {sorted(TEMPORAL_TYPES)} is removed.",
            _drop_temporal_fields,
        ),
        Defect("drop-media-types", "The declared media types are removed.", _drop_media_types),
        Defect(
            "drop-themes-keywords",
            "Themes and keywords are removed; title, description and fields remain.",
            _drop_themes_keywords,
        ),
        Defect("empty-all", "Everything but the schema class is removed.", _empty_all),
        Defect(
            "off-domain",
            "Title, description, keywords and themes are replaced with text about Welsh "
            "poetry manuscripts; fields and media types remain.",
            _off_domain,
        ),
        Defect("unhelpful-title", "The title is replaced with 'Dataset 1'.", _unhelpful_title),
    )
}


def apply_defect(name: str, doc: Document) -> Document:
    """A copy of `doc` with the defect `name` applied. An unknown name raises `KeyError`."""
    return DEFECTS[name].apply(copy.deepcopy(doc))

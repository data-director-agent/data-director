"""Requirement sets for the tests, written where a test chooses (ADR-0038)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dd_harness.requirements import DATACITE

ORDA = "r3d100012124"
ELSEWHERE = "r3d100000001"


def standard(**changes: Any) -> dict[str, Any]:
    return {
        "schema_class": "RequirementSet",
        "requirement_set_id": "datacite-4",
        "version": 1,
        "title": "DataCite Metadata Schema 4",
        "conforms_to": DATACITE,
        "re3data_names": ["DataCite Metadata Schema"],
        "fields": [
            {"property": "titles", "schema_org": "name", "obligation": "required"},
            {
                "property": "descriptions",
                "qualifier": {"descriptionType": "Abstract"},
                "schema_org": "description",
                "obligation": "recommended",
            },
        ],
        "required_documents": ["metadata_record"],
        **changes,
    }


def override(**changes: Any) -> dict[str, Any]:
    return {
        "schema_class": "RequirementSet",
        "requirement_set_id": "orda",
        "version": 2,
        "title": "ORDA",
        "conforms_to": DATACITE,
        "re3data_id": ORDA,
        "fields": [
            {
                "property": "titles",
                "schema_org": "name",
                "obligation": "required",
                "form_label": "Title",
            },
            {
                "property": "descriptions",
                "qualifier": {"descriptionType": "Abstract"},
                "schema_org": "description",
                "obligation": "required",
                "form_label": "Description",
            },
            {
                "property": "subjects",
                "schema_org": "keywords",
                "obligation": "required",
                "form_label": "Keywords",
            },
        ],
        "required_documents": ["metadata_record"],
        "recommended_documents": ["readme"],
        "media_types": [],
        "licences": ["CC-BY-4.0"],
        **changes,
    }


def write(root: Path, *sets: tuple[str, dict[str, Any]]) -> Path:
    for folder, document in sets:
        path = root / folder / f"{document['requirement_set_id']}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(document, sort_keys=False), "utf-8")
    return root

"""Requirement sets for the tests, and the pinned re3data export a choice is read from, written
where a test chooses (docs/specs/deposit.md)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from dd_harness.requirements import DATACITE
from dd_harness.sources import Sources

ORDA = "r3d100012124"
ELSEWHERE = "r3d100000001"
EXPORT = "re3data:export:2026-11"

# Records as the export's registry.jsonl holds them, cut down to the fields a choice reads.
RECORDS = (
    {"re3data_id": ORDA, "name": "ORDA", "metadata_standards": ["Dublin Core"]},
    {"re3data_id": ELSEWHERE, "name": "Elsewhere", "metadata_standards": []},
)


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


def registry(root: Path, records: tuple[dict[str, Any], ...] = RECORDS, ref: str = EXPORT) -> Path:
    """Write `records` as a re3data export and a `sources.yaml` pinning it under `ref`; returns
    the `sources.yaml`."""
    root.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records).encode()
    (root / "registry.jsonl").write_bytes(data)
    config = root / "sources.yaml"
    entry = {
        "snapshot_refs": [ref],
        "path": "registry.jsonl",
        "id_field": "re3data_id",
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    config.write_text(yaml.safe_dump({"sources": [entry]}), "utf-8")
    return config


def pinned(root: Path) -> Sources:
    """The sources of a `sources.yaml` that pins `RECORDS`."""
    return Sources.from_config(registry(root))

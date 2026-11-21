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

DURHAM = "bl.durham"
DATACITE_SNAPSHOT = "datacite:repositories:2026-11-21"

# Records as the export's registry.jsonl holds them, cut down to the fields a choice reads.
RECORDS = (
    {
        "re3data_id": ORDA,
        "name": "ORDA",
        "metadata_standards": ["Dublin Core"],
        "url": "https://orda.shef.ac.uk/",
    },
    {"re3data_id": ELSEWHERE, "name": "Elsewhere", "metadata_standards": []},
)
# Repositories as DataCite's snapshot holds them (agents/advisor-repository/data/datacite): one
# re3data does not list, and one at ORDA's address, which re3data describes.
DATACITE_RECORDS = (
    {
        "datacite_id": DURHAM,
        "name": "Durham University Repositories",
        "alternate_name": None,
        "url": "https://researchdata.durham.ac.uk/",
        "dataset_count": "611",
    },
    {
        "datacite_id": "bl.shef",
        "name": "ORDA on DataCite",
        "alternate_name": None,
        "url": "http://www.orda.shef.ac.uk",
        "dataset_count": "2092",
    },
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


def _pinned(
    root: Path, name: str, records: tuple[dict[str, Any], ...], **entry: Any
) -> dict[str, Any]:
    data = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records).encode()
    (root / name).write_bytes(data)
    return {**entry, "path": name, "sha256": hashlib.sha256(data).hexdigest()}


def registry(
    root: Path,
    records: tuple[dict[str, Any], ...] = RECORDS,
    ref: str = EXPORT,
    datacite: tuple[dict[str, Any], ...] = (),
) -> Path:
    """Write `records` as a re3data export, and `datacite` as a DataCite snapshot, and a
    `sources.yaml` pinning them, the export under `ref`; returns the `sources.yaml`."""
    root.mkdir(parents=True, exist_ok=True)
    entries = [_pinned(root, "registry.jsonl", records, snapshot_refs=[ref], id_field="re3data_id")]
    if datacite:
        entries.append(
            _pinned(
                root,
                "repositories.jsonl",
                datacite,
                snapshot_refs=[DATACITE_SNAPSHOT],
                id_field="datacite_id",
            )
        )
    config = root / "sources.yaml"
    config.write_text(yaml.safe_dump({"sources": entries}), "utf-8")
    return config


def pinned(root: Path) -> Sources:
    """The sources of a `sources.yaml` that pins `RECORDS`."""
    return Sources.from_config(registry(root))

"""Generating `schemas/*.json` from the Pydantic models.

§6 says the JSON Schemas are written before any code and are definitive. Keeping two
definitions in step by hand is the kind of discipline that lasts about a month, so the models
are the single source of truth and the schema files are generated from them and committed.
`test_schemas_current` byte-compares a regeneration against what is on disk, which makes the
committed files authoritative-by-construction for anything outside Python.

Canonical form — sorted keys, two-space indent, trailing newline — so the comparison is a
byte comparison and a diff is a real change rather than a formatting difference.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from standards_advisor.models.profile import DatasetProfile
from standards_advisor.models.provenance import ProvDocument
from standards_advisor.models.recommendations import RecommendationsDocument

#: Published document types and their filenames. Internal stage payloads are deliberately
#: absent — they are not part of the §6 contract and should not look like they are.
EXPORTS: dict[str, type[BaseModel]] = {
    "dataset-profile.schema.json": DatasetProfile,
    "recommendations.schema.json": RecommendationsDocument,
    "provenance.schema.json": ProvDocument,
}


def render(model: type[BaseModel]) -> str:
    """The canonical serialisation of one model's JSON Schema."""
    schema = model.model_json_schema(by_alias=True, mode="serialization")
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def expected() -> dict[str, str]:
    """Filename → canonical content, for every published schema."""
    return {name: render(model) for name, model in EXPORTS.items()}


def write_schemas(schemas_root: Path) -> list[Path]:
    """Write every schema, returning the paths that changed."""
    schemas_root.mkdir(parents=True, exist_ok=True)
    changed: list[Path] = []
    for name, content in expected().items():
        path = schemas_root / name
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            path.write_text(content, encoding="utf-8")
            changed.append(path)
    return changed


def drift(schemas_root: Path) -> dict[str, str]:
    """Filename → what is wrong with it, for every schema that is missing or out of date."""
    problems: dict[str, str] = {}
    for name, content in expected().items():
        path = schemas_root / name
        if not path.is_file():
            problems[name] = "missing"
        elif path.read_text(encoding="utf-8") != content:
            problems[name] = "out of date"
    return problems

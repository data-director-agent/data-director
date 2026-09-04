"""The committed JSON Schemas must match the Pydantic models.

§6 says the schemas are definitive. Since they are generated, "definitive" only holds if a model
change without a regeneration is caught — otherwise the published contract quietly drifts from
the code that produces the documents.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from standards_advisor.schema_export import EXPORTS, drift, expected


def test_no_committed_schema_is_missing_or_out_of_date(project_root: Path):
    problems = drift(project_root / "schemas")
    assert not problems, (
        "committed schemas differ from the models: "
        + ", ".join(f"{name} ({why})" for name, why in sorted(problems.items()))
        + " — run: uv run python scripts/export_schemas.py"
    )


@pytest.mark.parametrize("name", sorted(EXPORTS))
def test_each_schema_is_itself_valid_json_schema(name: str, project_root: Path):
    schema = json.loads((project_root / "schemas" / name).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)


def test_generation_is_deterministic():
    """Canonical form — sorted keys, fixed indent — so a diff is a real change."""
    assert expected() == expected()


def test_internal_stage_payloads_are_not_published():
    """They cross node boundaries but are not part of the §6 contract, and publishing them
    would imply a stability promise there is no reason to make."""
    published = {model.__name__ for model in EXPORTS.values()}
    assert published == {"DatasetProfile", "RecommendationsDocument", "ProvDocument"}

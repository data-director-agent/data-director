"""A whole run on the sample dataset, with no registry and no model.

This is the regression baseline. Every registry route added later has to keep this document
honest: the profile is real, the abstentions state accurately that no search ran, and nothing
claims more than it knows.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from standards_advisor.models.common import RecommendationKind
from standards_advisor.models.profile import ColumnType
from standards_advisor.models.recommendations import NothingFoundReason
from standards_advisor.runner import run_pipeline
from standards_advisor.settings import Settings


@pytest.fixture
def result(settings: Settings, sample_input):
    return run_pipeline(settings, sample_input, use_checkpoints=False)


def test_the_run_completes_and_produces_a_document(result):
    assert result.document is not None
    # A run that declines everything is a good run (§5.5), so it must not report as incomplete.
    assert result.manifest.exit_status != "incomplete"


def test_the_profile_types_every_column_with_a_recorded_derivation(result, settings):
    profile = json.loads((result.run_dir.file("profile")).read_text(encoding="utf-8"))
    columns = {column["name"]: column for column in profile["columns"]}

    assert len(columns) == 14
    for column in columns.values():
        assert column["inferred_type"]
        assert column["type_derivation"] == "local_parse"

    # The findings R3.4 exists to produce.
    assert columns["collection_date"]["inferred_type"] == ColumnType.DATE
    assert columns["collection_date"]["pattern"] == "%Y-%m-%d"
    assert columns["survey_date_uk"]["pattern"] == "%d/%m/%Y"
    assert columns["sampled_at"]["inferred_type"] == ColumnType.DATETIME
    assert columns["latitude"]["inferred_type"] == ColumnType.COORDINATE
    assert columns["organic_carbon_pct"]["unit"] == "pct"
    assert columns["analyst_orcid"]["inferred_type"] == ColumnType.IDENTIFIER
    assert columns["soil_horizon"]["inferred_type"] == ColumnType.CATEGORICAL


def test_metadata_supplied_with_the_dataset_is_used(result):
    assert result.document is not None
    profile = json.loads((result.run_dir.file("profile")).read_text(encoding="utf-8"))
    assert "upland grassland" in (profile["title"] or "")
    assert profile["keywords"]


def test_every_kind_is_accounted_for(result):
    """R3.6, structurally: `assemble` iterates the enum, so no kind can be silently omitted."""
    document = result.document
    assert document is not None
    covered = {item.kind for item in document.recommendations} | {
        item.kind for item in document.nothing_found
    }
    assert covered == set(RecommendationKind)


def test_no_recommendations_and_four_honest_abstentions(result):
    document = result.document
    assert document is not None
    assert document.recommendations == []
    assert len(document.nothing_found) == 4

    for absence in document.nothing_found:
        # The truthful reason: no registry was available, so no search ran. Reporting
        # "we searched and found nothing" here would be a lie.
        assert absence.reason is NothingFoundReason.REGISTRY_UNAVAILABLE
        assert "no search actually ran" in absence.statement
        assert absence.referral
        assert absence.searched.registry_snapshot is not None
        assert absence.searched.registry_snapshot.stale is True


def test_the_abstention_still_says_what_would_have_been_searched(result):
    """The four §5.2 queries are built for real even though none of them ran."""
    document = result.document
    assert document is not None
    for absence in document.nothing_found:
        assert absence.searched.queries, f"{absence.kind} recorded no query"
        assert any(absence.kind.value in query for query in absence.searched.queries)


def test_the_document_requires_human_review(result):
    assert result.document is not None
    assert result.document.requires_human_review is True


def test_the_document_validates_against_the_committed_schema(result, project_root: Path):
    """The committed JSON Schema is the published contract, so the run must satisfy it."""
    schema = json.loads(
        (project_root / "schemas" / "recommendations.schema.json").read_text(encoding="utf-8")
    )
    payload = json.loads(result.run_dir.file("recommendations").read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)


def test_the_profile_validates_against_the_committed_schema(result, project_root: Path):
    schema = json.loads(
        (project_root / "schemas" / "dataset-profile.schema.json").read_text(encoding="utf-8")
    )
    payload = json.loads(result.run_dir.file("profile").read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)


def test_no_model_was_called(result):
    """Nothing on the v0.1 path needs a key, which is why the suite runs with sockets off."""
    assert result.manifest.model.calls == 0

"""A whole pre-collection run, with no registry, no model and no data (§8).

The counterpart of `test_graph_end_to_end` for the Blueprint's first entry point, and the same
regression baseline: the profile is real, the abstentions state accurately that no search ran,
and nothing claims more than it knows. Every registry route added later has to keep this honest
too.

The run declines all four kinds, because `DD_REGISTRY_ROUTE` defaults to `empty` and that route
refuses to search. That is the correct v0.1 outcome and the point of the test is what sits
underneath it: sixteen variables read out of a data dictionary for a dataset that does not exist.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from standards_advisor.models.common import LifecyclePhase, RecommendationKind, StageName
from standards_advisor.models.profile import ColumnType, DatasetProfile
from standards_advisor.models.recommendations import NothingFoundReason, TargetKind
from standards_advisor.nodes.retrieve import build_queries
from standards_advisor.runner import run_pipeline
from standards_advisor.settings import Settings


@pytest.fixture
def result(settings: Settings, planned_input):
    return run_pipeline(settings, planned_input, use_checkpoints=False)


def test_the_run_completes_and_produces_a_document(result):
    assert result.document is not None
    assert not result.awaiting_input
    assert result.manifest.exit_status != "incomplete"


def test_the_document_and_profile_record_the_phase(result):
    """In the document, not only the manifest.

    It changes how every entry should be read: pre-collection advice is a decision to make,
    collected advice is a change to make. A viewer showing one as the other would be wrong in a
    way the reader could not detect.
    """
    assert result.document.phase is LifecyclePhase.PRE_COLLECTION
    profile = json.loads(result.run_dir.file("profile").read_text(encoding="utf-8"))
    assert profile["phase"] == "pre_collection"
    assert profile["source"]["kind"] == "planned_documentation"


def test_the_profile_is_built_from_documentation_and_reads_no_data(result):
    profile = json.loads(result.run_dir.file("profile").read_text(encoding="utf-8"))

    assert profile["files"] == [], "there are no files yet, and that is not a fault"
    assert profile["formats_found"] == []
    assert len(profile["columns"]) == 16
    for column in profile["columns"]:
        assert column["type_derivation"] == "declared_in_data_dictionary"
        assert column["example_values"] == [], "no data exists, so no value can have been seen"

    stage = next(report for report in result.manifest.stages if report.stage is StageName.PROFILE)
    assert stage.counts["files"] == 0
    assert stage.counts["planned_variables"] == 16


def test_the_readme_supplies_the_title_and_abstract_with_a_derivation(result):
    """§6.1: everything inferred records how. These are parsed from prose, not supplied."""
    profile = json.loads(result.run_dir.file("profile").read_text(encoding="utf-8"))

    assert "restoration monitoring" in profile["title"]
    assert profile["title_derivation"] == "local_parse"
    assert profile["abstract_derivation"] == "local_parse"
    assert "upland grassland" in profile["keywords"]


def test_the_intake_answers_become_the_search_facets(result):
    """The whole reason `elicit` exists: with no data, these cannot be inferred at all."""
    profile = json.loads(result.run_dir.file("profile").read_text(encoding="utf-8"))

    assert [term["term"] for term in profile["subjects"]] == [
        "Environmental Science",
        "Soil Science",
    ]
    assert profile["fields_of_research"]
    assert profile["entity_scope"]
    assert all(term["derivation"] == "researcher_answer" for term in profile["subjects"])
    assert all(term["list_name"] is None for term in profile["subjects"])
    assert profile["formats_planned"] == ["csv", "xlsx"]
    assert [v["name"] for v in profile["measured_variables"]] == [
        "pH",
        "organic carbon",
        "total nitrogen",
        "sward height",
    ]


def test_an_unanswered_question_leaves_the_field_empty_rather_than_invented(result):
    """`target_repository` is deliberately unanswered in the sample.

    Pre-collection that is the honest answer more often than not — the Blueprint puts repository
    selection in phase 3 — and the §5.3 repository-fit rule is specified to be skipped when the
    profile names none, not scored zero.
    """
    profile = json.loads(result.run_dir.file("profile").read_text(encoding="utf-8"))
    assert profile["target_repository"] is None


def test_declared_field_level_findings_survive_into_the_queries(result):
    """R3.4's inputs, one phase earlier than usual and entirely from declarations."""
    profile = json.loads(result.run_dir.file("profile").read_text(encoding="utf-8"))
    columns = {column["name"]: column for column in profile["columns"]}

    assert columns["survey_date"]["pattern"] == "%d/%m/%Y"
    assert columns["survey_date"]["inferred_type"] == ColumnType.DATE
    assert columns["waterlogged"]["inferred_type"] == ColumnType.BOOLEAN
    assert columns["latitude"]["inferred_type"] == ColumnType.COORDINATE
    assert columns["total_nitrogen"]["unit"] == "mg/kg"
    assert columns["soil_horizon"]["permitted_values"] == ["O", "A", "B"]


def test_an_unmappable_declared_type_is_reported_and_not_searched_for(result):
    """The refusal path reaching the run record.

    A structured field filed as free text would be given text advice that does not apply, so it
    becomes `unknown`, a failure says why, and no field-level target is built for it.
    """
    profile = json.loads(result.run_dir.file("profile").read_text(encoding="utf-8"))
    columns = {column["name"]: column for column in profile["columns"]}
    assert columns["quadrat_species_cover"]["inferred_type"] == ColumnType.UNKNOWN

    assert any(failure.kind == "declared_type_unmapped" for failure in result.manifest.failures)

    field_level = next(
        absence
        for absence in result.document.nothing_found
        if absence.kind is RecommendationKind.FIELD_LEVEL_STANDARD
    )
    targets = " ".join(field_level.searched.queries)
    assert "quadrat_species_cover" not in targets


def test_column_targets_are_planned_variables_not_field_values(result):
    """Advice about values that exist and values not yet recorded are acted on differently.

    Asserted against the queries the retriever built, rather than the abstention's `describe()`
    strings, because `RegistryQuery.describe()` records facets and filters but not targets.
    """
    profile = DatasetProfile.model_validate(
        json.loads(result.run_dir.file("profile").read_text(encoding="utf-8"))
    )
    queries = {query.kind: query for query in build_queries(profile)}

    vocabulary = queries[RecommendationKind.CONTROLLED_VOCABULARY_LINKAGE]
    assert vocabulary.targets, "the declared enumerations should have produced targets"
    assert {target.kind for target in vocabulary.targets} == {TargetKind.PLANNED_VARIABLE}
    assert {target.field for target in vocabulary.targets} == {
        "soil_horizon",
        "restoration_treatment",
    }

    field_level = queries[RecommendationKind.FIELD_LEVEL_STANDARD]
    assert {target.kind for target in field_level.targets} == {TargetKind.PLANNED_VARIABLE}
    assert "quadrat_species_cover" not in {target.field for target in field_level.targets}


def test_the_format_search_uses_planned_formats(result):
    """R3.3 at its cheapest: the researcher plans to write XLSX and has written nothing."""
    absence = next(
        item
        for item in result.document.nothing_found
        if item.kind is RecommendationKind.OPEN_FORMAT
    )
    assert absence.searched.facets.get("format_planned") == ["csv", "xlsx"]
    assert "format" not in absence.searched.facets


def test_every_kind_is_accounted_for(result):
    """R3.6's mechanism, unchanged by the new phase."""
    document = result.document
    covered = {item.kind for item in document.recommendations} | {
        item.kind for item in document.nothing_found
    }
    assert covered == set(RecommendationKind)


def test_no_recommendations_and_four_honest_abstentions(result):
    document = result.document
    assert document.recommendations == []
    assert len(document.nothing_found) == 4
    for absence in document.nothing_found:
        assert absence.reason is NothingFoundReason.REGISTRY_UNAVAILABLE
        assert "no search actually ran" in absence.statement
        assert absence.referral


def test_phase_four_advice_is_marked_as_brought_forward(result):
    """The Blueprint puts open formats in phase 4 (Figure 4), vocabularies in phase 1.

    A pre-collection run answers all four anyway, because format advice is cheapest before
    anything is written — but the deviation is stated in the output rather than only in a design
    document, so a reader can see it was deliberate.
    """
    by_kind = {absence.kind: absence for absence in result.document.nothing_found}

    open_format = by_kind[RecommendationKind.OPEN_FORMAT]
    assert open_format.brought_forward_from_phase == 4
    assert "phase 4" in open_format.statement

    vocabulary = by_kind[RecommendationKind.CONTROLLED_VOCABULARY_LINKAGE]
    assert vocabulary.brought_forward_from_phase is None
    assert "phase 4" not in vocabulary.statement


def test_the_referrals_are_the_pre_collection_ones(result):
    """Before collection the action is a decision, not a migration, so the advice differs."""
    vocabulary = next(
        absence
        for absence in result.document.nothing_found
        if absence.kind is RecommendationKind.CONTROLLED_VOCABULARY_LINKAGE
    )
    assert "Before you start collecting" in vocabulary.referral
    assert "data management plan" in vocabulary.referral


def test_the_document_requires_human_review(result):
    assert result.document.requires_human_review is True


def test_both_documents_validate_against_the_committed_schemas(result, settings: Settings):
    schemas = settings.schemas_root
    for name, key in (
        ("dataset-profile.schema.json", "profile"),
        ("recommendations.schema.json", "recommendations"),
    ):
        schema = json.loads(Path(schemas / name).read_text(encoding="utf-8"))
        payload = json.loads(result.run_dir.file(key).read_text(encoding="utf-8"))
        jsonschema.validate(payload, schema)


def test_no_model_was_called(result):
    assert result.manifest.model.calls == 0


def test_the_intake_question_set_is_recorded(result):
    """R10: which questions were in force is part of what happened."""
    assert result.manifest.intake_config is not None
    assert result.manifest.intake_config.version == "intake.v1"
    assert len(result.manifest.intake_config.sha256) == 64


def test_the_provenance_graph_records_the_elicitation(result):
    """The answers steer every query the run makes, so the profile has to depend on them."""
    graph = json.loads(result.run_dir.file("provenance").read_text(encoding="utf-8"))["@graph"]
    labels = {node.get("prov:label") for node in graph}
    assert "intake question set" in labels
    assert "intake answers" in labels

    answers = next(node for node in graph if node.get("prov:label") == "intake answers")
    profile = next(node for node in graph if node.get("prov:label") == "dataset profile")
    assert answers["prov:wasGeneratedBy"].endswith("activity:elicit")
    assert answers["@id"] in profile["prov:wasDerivedFrom"]

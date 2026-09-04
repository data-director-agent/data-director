"""Reading a draft data dictionary as Frictionless Table Schema (§8).

The counterpart of `test_profiling_columns` for the pre-collection route. Tier 1 is tested by
feeding it values; this is tested by feeding it declarations, and the interesting cases are the
ones where a declaration is *not* enough — an unmappable type, a unit the standard has no place
for, and an enumeration that must not be mistaken for a measurement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from standards_advisor.models.common import Derivation
from standards_advisor.models.profile import ColumnType
from standards_advisor.planning import ParsedDictionary, read_dictionary
from tests.conftest import PLANNED_DICTIONARY


def _schema(tmp_path: Path, fields: list[dict[str, Any]], **extra: Any) -> ParsedDictionary:
    path = tmp_path / "dictionary.json"
    path.write_text(json.dumps({"fields": fields, **extra}), encoding="utf-8")
    return read_dictionary(path)


@pytest.fixture
def sample():
    return read_dictionary(PLANNED_DICTIONARY)


def test_every_field_becomes_a_column_declared_not_parsed(sample):
    assert len(sample.columns) == 16
    for column in sample.columns:
        assert column.type_derivation is Derivation.DECLARED_IN_DATA_DICTIONARY
        assert column.declared_type, "the declared type is kept verbatim, however it mapped"


def test_a_planned_column_has_no_observation_counts(sample):
    """The point of the optional counts: a plan is not a measurement.

    Reporting zero blanks for a column that has never been filled in would be a statement about
    data that does not exist, and a ranking rule could not tell it from a real observation.
    """
    for column in sample.columns:
        assert column.sample_size is None
        assert column.blank_count is None
        assert column.blank_proportion is None
        assert column.distinct_count is None
        assert column.distinct_count_is_exact is None
        assert column.example_values == []


def test_declared_types_map_onto_column_types(sample):
    types = {column.name: column.inferred_type for column in sample.columns}
    assert types["survey_date"] is ColumnType.DATE
    assert types["survey_start_time"] is ColumnType.TIME
    assert types["survey_duration"] is ColumnType.DURATION
    assert types["survey_year"] is ColumnType.DATE
    assert types["waterlogged"] is ColumnType.BOOLEAN
    assert types["plot_id"] is ColumnType.IDENTIFIER
    assert types["surveyor_notes"] is ColumnType.FREE_TEXT


def test_a_declared_non_iso_date_format_is_kept_as_a_pattern(sample):
    """R3.4's whole reason for existing, one phase earlier.

    "It is a date" is not actionable; "it is `%d/%m/%Y`, use ISO 8601" is — and pre-collection
    the fix is a line in a data dictionary rather than a migration.
    """
    column = next(c for c in sample.columns if c.name == "survey_date")
    assert column.pattern == "%d/%m/%Y"


def test_a_default_format_is_filled_in_from_the_standard(sample):
    """`survey_start_time` declares no format, so the standard's own ISO form applies."""
    column = next(c for c in sample.columns if c.name == "survey_start_time")
    assert column.pattern == "%H:%M:%S"


def test_a_coarse_date_type_carries_the_pattern_that_makes_it_actionable(sample):
    column = next(c for c in sample.columns if c.name == "survey_year")
    assert column.pattern == "%Y"


def test_a_declared_enumeration_becomes_categorical_with_its_values_kept(sample):
    """R3.1's target, and the §1.4 carve-out: these values may reach a model."""
    column = next(c for c in sample.columns if c.name == "soil_horizon")
    assert column.inferred_type is ColumnType.CATEGORICAL
    assert column.permitted_values == ["O", "A", "B"]


def test_an_enumeration_is_not_recorded_as_a_distinct_value_count(sample):
    """A codebook says what *may* be recorded, not what was.

    Writing `len(enum)` into `distinct_count` would let `ranking.rules.type_match` read a
    declaration as a measurement, which is the one confusion this whole route has to avoid.
    """
    column = next(c for c in sample.columns if c.name == "soil_horizon")
    assert column.permitted_values
    assert column.distinct_count is None
    assert column.distinct_count_is_exact is None


def test_an_enumeration_beats_the_underlying_type(tmp_path):
    """A coded integer needs a vocabulary far more than it needs a number format."""
    parsed = _schema(
        tmp_path,
        [{"name": "land_class", "type": "integer", "constraints": {"enum": ["1", "2", "3"]}}],
    )
    assert parsed.columns[0].inferred_type is ColumnType.CATEGORICAL


def test_a_declared_unit_outranks_one_read_from_the_column_name(sample):
    """R5 names units as researcher-supplied, so a declaration is the stronger derivation."""
    declared = next(c for c in sample.columns if c.name == "total_nitrogen")
    assert (declared.unit, declared.unit_derivation) == (
        "mg/kg",
        Derivation.DECLARED_IN_DATA_DICTIONARY,
    )

    from_name = next(c for c in sample.columns if c.name == "organic_carbon_pct")
    assert (from_name.unit, from_name.unit_derivation) == ("pct", Derivation.LOCAL_PARSE)
    assert from_name.inferred_type is ColumnType.QUANTITY_WITH_UNIT


def test_a_unit_is_not_invented_for_a_type_that_cannot_have_one(sample):
    """`survey_year` would otherwise be reported as a quantity measured in years.

    `unit_from_column_name` recognises `year` as a unit, so the heuristic has to be restricted
    to types a magnitude can belong to. A date is not a magnitude.
    """
    column = next(c for c in sample.columns if c.name == "survey_year")
    assert column.unit is None
    assert column.unit_derivation is None


def test_coordinates_are_recognised_from_the_name_when_the_type_is_only_number(sample):
    """The declared type says `number`; only the name reveals that ISO 6709 applies."""
    for name in ("latitude", "longitude"):
        column = next(c for c in sample.columns if c.name == name)
        assert column.inferred_type is ColumnType.COORDINATE


def test_an_unmappable_type_is_refused_not_guessed(sample):
    """The refusal path, and the reason `ColumnType.UNKNOWN` exists.

    Filing a structured field as free text and recommending a text standard would be worse than
    saying nothing — the failure R3.6 exists to prevent, one level down.
    """
    column = next(c for c in sample.columns if c.name == "quadrat_species_cover")
    assert column.inferred_type is ColumnType.UNKNOWN
    assert column.declared_type == "object"
    assert any(finding.kind == "declared_type_unmapped" for finding in sample.findings)


def test_variable_definitions_are_kept(sample):
    """First in R5's list of what "cannot be inferred and require direct researcher input"."""
    column = next(c for c in sample.columns if c.name == "ph")
    assert column.description == "Soil pH measured in water suspension."


def test_missing_values_are_dataset_level_and_keep_the_empty_string(sample):
    """Table Schema declares `missingValues` per schema, and `""` is a real declaration.

    "A blank cell means missing" and "we have no convention for blank cells" are different
    statements, so the empty string must survive the read.
    """
    assert sample.missing_value_codes == ["", "NA", "-999"]
    for column in sample.columns:
        assert column.missing_value_codes == [], (
            "a schema-level declaration must not be copied onto every column as a per-field fact"
        )


def test_a_per_field_missing_value_declaration_is_kept_on_the_column(tmp_path):
    parsed = _schema(tmp_path, [{"name": "ph", "type": "number", "missingValues": ["-999"]}])
    assert parsed.columns[0].missing_value_codes == ["-999"]


def test_an_unreadable_dictionary_is_reported_not_raised(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ not json", encoding="utf-8")
    parsed = read_dictionary(path)
    assert parsed.columns == []
    assert any(finding.kind == "dictionary_unreadable" for finding in parsed.findings)


def test_a_dictionary_with_no_fields_is_reported_not_raised(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"title": "nothing here"}), encoding="utf-8")
    parsed = read_dictionary(path)
    assert parsed.columns == []
    assert any(finding.kind == "dictionary_has_no_fields" for finding in parsed.findings)


def test_a_missing_dictionary_is_reported_not_raised(tmp_path):
    parsed = read_dictionary(tmp_path / "absent.json")
    assert parsed.columns == []
    assert parsed.findings


def test_an_unnamed_field_is_dropped_with_a_finding(tmp_path):
    parsed = _schema(tmp_path, [{"type": "string"}, {"name": "ph", "type": "number"}])
    assert [column.name for column in parsed.columns] == ["ph"]
    assert any(finding.kind == "dictionary_field_unnamed" for finding in parsed.findings)


def test_an_unusual_but_valid_date_pattern_is_noted_not_failed(tmp_path):
    """A pattern tier 1 does not recognise is the finding, not an error."""
    parsed = _schema(tmp_path, [{"name": "d", "type": "date", "format": "%j-%Y"}])
    assert parsed.columns[0].pattern == "%j-%Y"
    assert parsed.notes
    assert not parsed.findings


def test_format_any_declines_to_name_a_pattern(tmp_path):
    """`any` means the schema will not say, so neither do we — ISO is not assumed."""
    parsed = _schema(tmp_path, [{"name": "d", "type": "date", "format": "any"}])
    assert parsed.columns[0].inferred_type is ColumnType.DATE
    assert parsed.columns[0].pattern is None

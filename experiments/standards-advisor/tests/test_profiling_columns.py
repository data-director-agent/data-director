"""Column type inference (§5.1 tier 1) — the one genuinely implemented stage.

R3.4 rests entirely on this, so these are the tests that would actually catch a regression in
the current codebase. The precedence cases at the end matter as much as the happy paths: most of
the ways this can be wrong are a correct answer arrived at in the wrong order.
"""

from __future__ import annotations

import pytest

from standards_advisor.models.profile import ColumnType
from standards_advisor.profiling.columns import infer_type, profile_column


@pytest.mark.parametrize(
    ("name", "values", "expected", "pattern"),
    [
        ("collection_date", ["2024-05-14", "2024-06-03"], ColumnType.DATE, "%Y-%m-%d"),
        ("survey_date_uk", ["14/05/2024", "03/06/2024"], ColumnType.DATE, "%d/%m/%Y"),
        ("d", ["14 May 2024", "03 June 2024"], ColumnType.DATE, "%d %B %Y"),
        ("compact", ["20240514", "20240603"], ColumnType.DATE, "%Y%m%d"),
        (
            "sampled_at",
            ["2024-05-14T09:12:00+01:00", "2024-05-15T08:55:00+01:00"],
            ColumnType.DATETIME,
            "%Y-%m-%dT%H:%M:%S%z",
        ),
        # %z covers a literal "Z" as well as an offset, so both report the same format.
        ("utc", ["2024-05-14T09:12:00Z"], ColumnType.DATETIME, "%Y-%m-%dT%H:%M:%S%z"),
        ("naive", ["2024-05-14T09:12:00"], ColumnType.DATETIME, "%Y-%m-%dT%H:%M:%S"),
    ],
)
def test_dates_report_the_format_that_matched(name, values, expected, pattern):
    """Naming the format is the point, not just recognising a date.

    "This is a date" is not actionable advice; "this is %d/%m/%Y, ISO 8601 wants %Y-%m-%d" is.
    """
    inferred, matched, unit = infer_type(name, values)
    assert inferred is expected
    assert matched == pattern
    assert unit is None


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("0000-0002-1825-0097", "orcid"),
        ("https://orcid.org/0000-0002-1825-0097", "orcid"),
        ("10.25504/FAIRsharing.fj07xj", "doi"),
        ("https://doi.org/10.25504/FAIRsharing.fj07xj", "doi"),
        ("PDS-2024-001", "accession"),
        ("f81d4fae-7dec-11d0-a765-00a0c91e6bf6", "uuid"),
    ],
)
def test_identifiers_are_recognised_and_named(value, kind):
    inferred, matched, _ = infer_type("some_id", [value, value, value])
    assert inferred is ColumnType.IDENTIFIER
    assert matched == kind


def test_coordinates_need_both_the_name_and_the_range():
    """A column called `x` is not a coordinate merely because it is called `x`."""
    inferred, pattern, _ = infer_type("latitude", ["53.3421", "53.3418", "-12.5"])
    assert inferred is ColumnType.COORDINATE
    assert pattern == "decimal_degrees"

    # Right name, impossible latitude — must not be claimed as a coordinate.
    out_of_range, _, _ = infer_type("latitude", ["153.3421", "142.0", "99.9"])
    assert out_of_range is ColumnType.NUMBER

    # Plausible values, but nothing in the name suggests a coordinate.
    unnamed, _, _ = infer_type("ph", ["4.8", "5.1", "5.6"])
    assert unnamed is ColumnType.NUMBER


@pytest.mark.parametrize(
    ("name", "expected_unit"),
    [
        ("organic_carbon_pct", "pct"),
        ("bulk_density_g_cm3", "g_cm3"),
        ("depth_cm", "cm"),
        ("mass_kg", "kg"),
    ],
)
def test_a_unit_in_the_header_is_a_finding(name, expected_unit):
    """A unit documented in the column name rather than declared is what R3.4 is for."""
    inferred, pattern, unit = infer_type(name, ["11.2", "7.4", "2.1"])
    assert inferred is ColumnType.QUANTITY_WITH_UNIT
    assert pattern == "unit_in_header"
    assert unit == expected_unit


def test_a_unit_in_the_value_is_also_found():
    inferred, pattern, unit = infer_type("concentration", ["12.4 mg/L", "8.1 mg/L", "3 mg/L"])
    assert inferred is ColumnType.QUANTITY_WITH_UNIT
    assert pattern == "unit_in_value"
    assert unit == "mg/L"


def test_plain_numbers_carry_no_unit():
    inferred, pattern, unit = infer_type("total_nitrogen", ["0.41", "0.29", "0.11"])
    assert inferred is ColumnType.NUMBER
    assert pattern is None
    assert unit is None


def test_low_cardinality_with_repetition_is_categorical():
    values = ["O", "A", "B"] * 8
    inferred, _, _ = infer_type("soil_horizon", values)
    assert inferred is ColumnType.CATEGORICAL


def test_short_codes_are_not_mistaken_for_accessions():
    """`soil_horizon` (`O`/`A`/`B`) must not match the accession pattern.

    The accession regex requires a separator precisely so that a three-value category system is
    not sent to the R3.4 field-level search instead of the R3.1 vocabulary search.
    """
    inferred, _, _ = infer_type("soil_horizon", ["O", "A", "B"] * 8)
    assert inferred is not ColumnType.IDENTIFIER


def test_identifier_beats_low_cardinality():
    """Three ORCIDs across forty rows is not a category system.

    Cardinality alone would call this categorical, which would offer a controlled vocabulary
    for a column of author identifiers. The pattern check has to run first.
    """
    values = ["0000-0002-1825-0097", "0000-0003-4641-2246", "0000-0001-5109-3700"] * 13
    inferred, matched, _ = infer_type("analyst_orcid", values)
    assert inferred is ColumnType.IDENTIFIER
    assert matched == "orcid"


def test_distinct_free_text_is_not_categorical():
    values = [f"a distinct note number {index}" for index in range(10)]
    inferred, _, _ = infer_type("notes", values)
    assert inferred is ColumnType.FREE_TEXT


def test_all_blank_is_empty_not_free_text():
    """There is nothing to recommend for an empty column, and saying so beats guessing."""
    inferred, _, _ = infer_type("unused", ["", "  ", ""])
    assert inferred is ColumnType.EMPTY


def test_a_genuinely_mixed_date_column_is_not_claimed_as_a_date():
    """Two formats splitting the column evenly should fall below the coverage threshold.

    Reporting the dominant format would be misleading here: half the values would silently not
    conform to the standard we recommended.
    """
    values = ["2024-05-14", "14 May 2024"] * 5
    inferred, _, _ = infer_type("messy_date", values)
    assert inferred is not ColumnType.DATE


def test_one_typo_does_not_demote_a_date_column():
    values = ["2024-05-14"] * 39 + ["not a date"]
    inferred, pattern, _ = infer_type("collection_date", values)
    assert inferred is ColumnType.DATE
    assert pattern == "%Y-%m-%d"


def test_counts_and_derivation_are_recorded():
    profile = profile_column(
        name="notes",
        position=3,
        file="data.csv",
        values=["a note", "", "  ", "another note", "a note"],
    )
    assert profile.sample_size == 5
    assert profile.blank_count == 2
    assert profile.blank_proportion == pytest.approx(0.4)
    assert profile.distinct_count == 2
    assert profile.type_derivation == "local_parse"


def test_distinct_counts_are_marked_inexact():
    """The pipeline only ever sees the head of a file.

    Recording this stops a later ranking rule mistaking a sample statistic for a population
    one — §6.1 asks for it explicitly.
    """
    profile = profile_column(name="x", position=0, file="d.csv", values=["1", "2"])
    assert profile.distinct_count_is_exact is False

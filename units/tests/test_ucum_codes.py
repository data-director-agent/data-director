"""A unit as a person writes it, and the UCUM code the rule gives it (dd_units.ucum)."""

from __future__ import annotations

import pytest

from dd_units import AMBIGUOUS, UcumUnit, means_no_unit, ucum_code, ucum_version


@pytest.mark.parametrize(
    ("written", "code"),
    [
        # UCUM names, in British spelling and in the plural
        ("micrometres", "um"),
        ("millilitres", "mL"),
        ("kilograms", "kg"),
        ("degrees Celsius", "Cel"),
        ("seconds", "s"),
        ("tonnes", "t"),
        # print symbols, the micro sign and the Greek mu (written as escapes, to tell them apart)
        ("°C", "Cel"),
        ("°F", "[degF]"),
        ("\u00b5m", "um"),
        ("\u03bcm", "um"),
        ("ppm", "[ppm]"),
        # common spellings UCUM does not list
        ("degC", "Cel"),
        ("deg C", "Cel"),
        ("micron", "um"),
        ("hrs", "h"),
        ("percent", "%"),
        ("hectares", "har"),
        # several terms, divided and multiplied
        ("mg per litre", "mg/L"),
        ("kg/m^3", "kg/m3"),
        ("kg m-3", "kg.m-3"),
        ("\u00b5mol m-2 s-1", "umol.m-2.s-1"),
        ("\u00b5S/cm", "uS/cm"),
        # powers written as superscripts and words
        ("m²", "m2"),
        ("square metres", "m2"),
        ("metres squared", "m2"),
        ("cubic metres", "m3"),
        # the most general of several units with one name
        ("feet", "[ft_i]"),
        ("pound", "[lb_av]"),
        # already UCUM, kept as written
        ("mg/L", "mg/L"),
        ("km/h", "km/h"),
        ("10*3/uL", "10*3/uL"),
        ("{cells}/mL", "{cells}/mL"),
        ("mC", "mC"),
    ],
)
def test_a_written_unit_has_its_ucum_code(written: str, code: str) -> None:
    unit = ucum_code(written)
    assert unit is not None
    assert unit.code == code


@pytest.mark.parametrize("written", sorted(AMBIGUOUS))
def test_a_code_people_read_otherwise_matches_nothing(written: str) -> None:
    assert ucum_code(written) is None


@pytest.mark.parametrize("written", ["pint", "gallon", "psu", "nonsense", "", "   ", "none"])
def test_an_unclear_or_unknown_unit_matches_nothing(written: str) -> None:
    assert ucum_code(written) is None


def test_a_unit_says_how_it_was_found_and_what_ucum_calls_it() -> None:
    assert ucum_code("um") == UcumUnit("um", "micrometre", "code")
    assert ucum_code("micrometres") == UcumUnit("um", "micrometre", "name")
    assert ucum_code("{cells}/mL") == UcumUnit("{cells}/mL", None, "code")


def test_every_code_returned_is_valid_ucum() -> None:
    from dd_units import _ucum

    for written in ("micrometres", "mg per litre", "square metres", "\u00b5S/cm", "feet"):
        unit = ucum_code(written)
        assert unit is not None
        assert _ucum.is_valid(unit.code)


def test_a_prefix_goes_only_on_a_metric_unit() -> None:
    # "ha" is not hecto-year: the year takes no prefix. It is the hectare, by its common spelling.
    unit = ucum_code("ha")
    assert unit is not None
    assert unit.code == "har"
    assert ucum_code("kfeet") is None


@pytest.mark.parametrize(
    ("written", "none"),
    [
        ("none", True),
        ("N/A", True),
        ("-", True),
        ("dimensionless.", True),
        ("1", False),
        ("m", False),
    ],
)
def test_no_unit_is_recognised(written: str, none: bool) -> None:
    assert means_no_unit(written) is none


def test_the_table_version_is_known() -> None:
    assert ucum_version()

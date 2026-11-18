"""A document is checked for possible personal data and secrets before it is attached, and what
is found never repeats what the document says (docs/specs/personal-data.md, #473)."""

from __future__ import annotations

import json
import re

import pytest

from dd_app.documentation_check import SECRET, kinds, screen

FLAGGED = """Notes for the README.
Contact jane.doe@example.org about the follow-up visit, or call 07700 900123.
aws_access_key_id = AKIAIOSFODNN7EXAMPLE
Soil cores were taken at 10 cm intervals.
"""


@pytest.mark.requirement("C2")
def test_personal_data_and_a_secret_are_found_by_kind() -> None:
    found = screen(FLAGGED)
    named = kinds(found)
    assert {"email address", "phone number"} <= set(named)
    assert any(f.kind == SECRET for f in found)


@pytest.mark.requirement("C2")
def test_no_value_nor_part_of_one_is_returned() -> None:
    returned = json.dumps([f.as_json() for f in screen(FLAGGED)])
    for value in ("jane.doe@example.org", "07700 900123", "AKIAIOSFODNN7EXAMPLE"):
        for token in {value, *re.findall(r"[A-Za-z0-9]{4,}", value)}:
            assert token not in returned, token


def test_ordinary_prose_gives_nothing() -> None:
    prose = (
        "Cores were taken at 10 cm intervals, weighed wet and dried at 105 C for 24 hours.\n"
        "Species were recorded on a 2 m quadrat at each site, following the protocol.\n"
    )
    assert screen(prose) == []


def test_each_kind_is_reported_once_however_often_it_occurs() -> None:
    text = "\n".join(f"Write to person{i}@example.org." for i in range(7))
    found = [f for f in screen(text) if f.kind == "email address"]
    assert len(found) == 1

"""The rule in scripts/check_adr_numbers.py that decision record numbers are unique."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_adr_numbers as can  # noqa: E402


def test_distinct_numbers_pass() -> None:
    assert can.shared_numbers(["0001-a.md", "0002-b.md", "README.md"]) == {}


def test_a_shared_number_is_reported() -> None:
    assert can.shared_numbers(["0037-b.md", "0037-a.md", "0038-c.md"]) == {
        "0037": ["0037-a.md", "0037-b.md"]
    }


def test_the_legacy_pair_is_allowed() -> None:
    assert can.shared_numbers(["0016-a.md", "0016-b.md"]) == {}

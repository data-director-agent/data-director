"""The detector comparison scores findings as it says it does (inventory/evals, #39). The scores
themselves are an evaluation's, not a test's: nothing here sets a threshold on them."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).parents[1] / "evals" / "compare_detectors.py"


@pytest.fixture(scope="module")
def compare() -> ModuleType:
    spec = importlib.util.spec_from_file_location("compare_detectors", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LABELS: dict[str, Any] = {
    "evaluation": [
        {"file": "e/a.csv", "column": "mail", "kind": "email address"},
        {"file": "e/a.csv", "column": "who", "kind": "person name", "needs": "needs NER"},
        {"file": "e/n.txt", "target": "text", "kind": "email address"},
        {"file": "e/n.txt", "target": "text", "kind": "phone number"},
    ],
    "evaluation_clean": [
        {"file": "e/a.csv", "column": "ref"},
        {"file": "e/m.md", "target": "text"},
    ],
}


def finding(file: str, target: str, kind: str, column: str | None = None) -> dict[str, Any]:
    made = {"finding_file": file, "finding_target": target, "finding_kind": kind}
    return {**made, "finding_column": column} if column else made


def test_a_place_counts_once_however_many_findings_it_has(compare: ModuleType) -> None:
    found = [finding("e/a.csv", "column", "email address", "mail")] * 3
    scored = compare.score(found, LABELS)
    assert scored["recall"]["email address"] == {"found": 1, "labelled": 2}
    assert scored["recall"]["phone number"]["found"] == 0


def test_a_finding_on_a_clean_place_is_a_false_positive(compare: ModuleType) -> None:
    found = [
        finding("e/a.csv", "column", "person name", "ref"),
        finding("e/m.md", "text", "location"),
    ]
    flagged = compare.score(found, LABELS)["false_positives"]
    assert flagged["clean_places"] == 2
    assert len(flagged["flagged"]) == 2


def test_kinds_labelled_at_a_place_are_not_counted_as_others(compare: ModuleType) -> None:
    found = [
        finding("e/n.txt", "text", "email address"),
        finding("e/n.txt", "text", "phone number"),
        finding("e/a.csv", "column", "location", "who"),
    ]
    scored = compare.score(found, LABELS)
    assert scored["other_kinds_on_labelled_places"] == {"location": 1}
    assert scored["needs_ner"] == ["person name"]


def test_names_found_by_header_are_not_counted_as_values(compare: ModuleType) -> None:
    found = [finding("e/a.csv", "field name", "direct identifier", "who")]
    scored = compare.score(found, LABELS)
    assert all(r["found"] == 0 for r in scored["recall"].values())


def test_a_timed_detector_counts_each_value_once(compare: ModuleType) -> None:
    class Nothing:
        description = "nothing"

        def analyse(self, text: str, context: list[str]) -> list[object]:
            return []

    timed = compare.Timed(Nothing())
    timed.analyse("a\nb\nc", [])
    assert timed.values == 3
    assert timed.seconds >= 0

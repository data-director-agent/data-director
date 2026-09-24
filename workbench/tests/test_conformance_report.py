"""The traceability rule and the report renderer, over a synthetic pytest-json-report."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import conformance_report as cr  # noqa: E402

REGISTER = [
    {"id": "R3", "source": "blueprint", "title": "Suggest"},
    {"id": "R3.6", "source": "project", "parent": "R3", "title": "Abstain"},
    {"id": "P14", "source": "blueprint", "title": "Low impact"},
    {"id": "C5", "source": "blueprint", "title": "Interop"},
]


def _report(tests: list[tuple[str, str, list[str]]]) -> dict:  # type: ignore[type-arg]
    return {
        "created": 1_800_000_000,
        "summary": {"passed": 2, "failed": 1, "skipped": 1, "total": 4},
        "tests": [
            {
                "nodeid": f"tests/test_x.py::{name}",
                "outcome": outcome,
                "metadata": {"requirements": ids},
            }
            for name, outcome, ids in tests
        ],
    }


def test_verdicts_follow_the_traceability_rule() -> None:
    report = _report(
        [
            ("test_a", "passed", ["R3"]),
            ("test_b", "failed", ["R3", "R3.6"]),
            ("test_c", "skipped", ["C5"]),
            ("test_d", "passed", ["ZZZ"]),
        ]
    )
    index = cr.tests_by_requirement(report)
    assert cr.verdict(index["R3"]) == cr.CONTRADICTED  # a failure outranks a pass
    assert cr.verdict(index["R3.6"]) == cr.CONTRADICTED
    assert cr.verdict(index["C5"]) == cr.UNSUBSTANTIATED  # skipped only
    assert cr.verdict(index.get("P14", [])) == cr.UNSUBSTANTIATED  # no test at all
    text = cr.render(REGISTER, report)
    assert "| P14 | blueprint | Low impact | ⬜ **unsubstantiated** | — |" in text
    assert "ZZZ" in text and "not in the register" in text
    assert "not** a conformance claim" in text


def test_check_compares_table_body_not_header(tmp_path: Path) -> None:
    report = _report([("test_a", "passed", ["R3"])])
    text = cr.render(REGISTER, report)
    out = tmp_path / "CONFORMANCE.md"
    out.write_text(text.replace("**Generated:**", "**Generated:** later "), encoding="utf-8")
    assert cr.table_body(out.read_text()) == cr.table_body(text)
    changed = cr.render(REGISTER, _report([("test_a", "failed", ["R3"])]))
    assert cr.table_body(changed) != cr.table_body(text)

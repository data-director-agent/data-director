"""The traceability rule, the review lane and the report renderer, over synthetic inputs."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import conformance_report as cr  # noqa: E402

REGISTER: list[dict[str, Any]] = [
    {"id": "R3", "source": "blueprint", "title": "Suggest"},
    {"id": "R3.6", "source": "project", "parent": "R3", "title": "Abstain"},
    {"id": "P14", "source": "blueprint", "title": "Low impact"},
    {"id": "C5", "source": "blueprint", "title": "Interop"},
    {"id": "C6", "source": "blueprint", "title": "Access", "assessed_by": ["test", "review"]},
    {"id": "C4", "source": "blueprint", "title": "Sovereignty", "assessed_by": ["review"]},
]


def _review(rid: str, verdict: str, day: int, reviewer: str = "A. Reviewer (Example)") -> dict:  # type: ignore[type-arg]
    return {
        "requirement": rid,
        "verdict": verdict,
        "reviewer": reviewer,
        "date": dt.date(2026, 10, day),
        "commit": "0123abcdef",
        "scope": "The viewer, by keyboard and screen reader.",
        "record": "https://example.org/notes",
    }


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
    assert (
        "| P14 | blueprint | Low impact | ⬜ **unsubstantiated** | — | not assessed | — |" in text
    )
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


def test_review_lane_reads_the_latest_review_and_stays_separate_from_tests() -> None:
    report = _report([("test_a", "passed", ["C6"])])
    reviews = [
        _review("C6", "meets", 1),
        _review("C6", "does-not-meet", 3, reviewer="B. Reviewer (Example)"),
        _review("C4", "meets", 2),
    ]
    latest = cr.latest_reviews(reviews)
    assert cr.review_verdict(latest["C6"]) == cr.CONTRADICTED  # the later review wins
    assert cr.review_verdict(latest.get("R3")) == cr.UNSUBSTANTIATED
    text = cr.render(REGISTER, report, reviews)
    # A passing test and a failing review sit side by side; neither overrides the other.
    assert (
        "| C6 | blueprint | Access | ✅ **substantiated** | `test_x::test_a` | "
        "❌ **contradicted** | "
        "B. Reviewer (Example), 2026-10-03, `0123abc`, [record](https://example.org/notes) |"
    ) in text
    assert "| C4 | blueprint | Sovereignty | not assessed | — | ✅ **substantiated** |" in text
    assert "| substantiated | 1 | 1 |" in text  # test lane: C6; review lane: C4
    assert "| contradicted | 0 | 1 |" in text


def test_same_named_tests_in_different_modules_are_told_apart() -> None:
    report = _report([("test_a", "passed", ["R3"])])
    report["tests"].append(
        {
            "nodeid": "agents/r3/tests/test_y.py::test_a",
            "outcome": "passed",
            "metadata": {"requirements": ["R3"]},
        }
    )
    text = cr.render(REGISTER, report)
    assert "`test_y::test_a`, `test_x::test_a`" in text  # sorted by node id


def test_a_test_claiming_a_review_only_requirement_is_flagged() -> None:
    text = cr.render(REGISTER, _report([("test_a", "passed", ["C4"])]))
    assert "assesses by review only: C4" in text


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"requirement": "C5"}, "not a registered requirement assessed by review"),
        ({"requirement": "ZZZ"}, "not a registered requirement assessed by review"),
        ({"verdict": "mostly"}, "verdict must be one of"),
        ({"date": "2026-10-01"}, "unquoted YYYY-MM-DD"),
        ({"commit": "HEAD"}, "hexadecimal"),
        ({"reviewer": ""}, "missing ['reviewer']"),
    ],
)
def test_a_malformed_review_is_refused(tmp_path: Path, change: dict, message: str) -> None:  # type: ignore[type-arg]
    import yaml

    entry = {**_review("C6", "meets", 1), **change}
    path = tmp_path / "reviews.yaml"
    path.write_text(yaml.safe_dump({"reviews": [entry]}), encoding="utf-8")
    with pytest.raises(cr.RegisterError, match=message.replace("[", r"\[").replace("]", r"\]")):
        cr.load_reviews(REGISTER, path)


def test_the_committed_register_and_review_record_load() -> None:
    register = cr.load_register()
    cr.load_reviews(register)
    assert all(cr.lanes(r) for r in register)

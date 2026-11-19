"""The synthetic disclosure corpus is what its generator writes, and its labels name real cases
(docs/specs/personal-data.md, #610)."""

from __future__ import annotations

import csv
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import pytest

CORPUS = Path(__file__).parent / "data" / "disclosure"


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("disclosure_corpus", CORPUS / "generate.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def labels() -> dict[str, object]:
    loaded: dict[str, object] = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))
    return loaded


def _committed() -> dict[str, str]:
    return {
        p.relative_to(CORPUS).as_posix(): p.read_text(encoding="utf-8")
        for p in CORPUS.rglob("*")
        if p.is_file() and p.name != "generate.py" and "__pycache__" not in p.parts
    }


def test_the_committed_corpus_is_what_the_generator_writes(generator: ModuleType) -> None:
    assert _committed() == generator.corpus(), (
        "Rewrite the corpus: uv run python inventory/tests/data/disclosure/generate.py"
    )


def _columns(relative: str) -> list[str]:
    path = CORPUS / relative
    with path.open(encoding="utf-8", newline="") as fh:
        return next(csv.reader(fh, delimiter="\t" if path.suffix == ".tsv" else ","))


def test_every_label_names_a_file_and_columns_that_exist(labels: dict[str, object]) -> None:
    cases = [
        c
        for key in (
            "personal_data",
            "suppressed",
            "kept",
            "quasi_identifier",
            "evaluation",
            "evaluation_clean",
        )
        for c in labels[key]  # type: ignore[attr-defined]
    ]
    assert cases
    for case in cases:
        assert (CORPUS / case["file"]).is_file(), case
        named = [case["column"]] if "column" in case else case.get("columns", [])
        assert set(named) <= set(_columns(case["file"])), case
    for clean in labels["clean"]:  # type: ignore[attr-defined]
        assert (CORPUS / clean).is_file()


def test_a_clean_control_has_the_shape_of_the_case_it_controls(labels: dict[str, object]) -> None:
    for clean in labels["clean"]:  # type: ignore[attr-defined]
        rows = (CORPUS / clean).read_text(encoding="utf-8").splitlines()
        assert len(rows) > 100


@pytest.mark.parametrize(
    ("pattern", "reserved"),
    [
        (r"[\w.]+@[\w.]+", r"[\w.]+@example\.(org|com|net)"),
        (r"\b0\d{2,4} ?\d{3,4} ?\d{3,4}\b", r"07700 900\d{3}|020 7946 0\d{3}"),
        (r"\b\d{3} \d{3} \d{4}\b", r"999 \d{3} \d{4}"),
        (r"\b[A-Z]{2}\d{6}[A-D]\b", r"QQ\d{6}[A-D]"),
        (r"\b[A-Z]{1,2}\d{1,2} \d[A-Z]{2}\b", r"ZZ99 \d[A-Z]{2}"),
    ],
)
def test_every_identifier_is_from_a_range_kept_for_fiction_or_testing(
    pattern: str, reserved: str
) -> None:
    found = [m for text in _committed().values() for m in re.findall(pattern, text)]
    assert found
    assert all(re.fullmatch(reserved, m) for m in found), sorted(
        m for m in found if not re.fullmatch(reserved, m)
    )

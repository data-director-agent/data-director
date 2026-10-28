"""The rule in scripts/check_todos.py that every unresolved marker names its issue."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_todos as ct  # noqa: E402

# Built from parts so that this file holds no marker of its own.
T = "TO" + "DO"


@pytest.mark.parametrize(
    "line",
    [
        f"# {T}(#123): settle the numbers",
        f"- {T}(#41, #57): how a steward edits the profile",
        f"(ADR-0025), {T}(#67).",
        f"{T}(#1) and {T}(#2)",
        "no marker here",
        "todo in lower case is ordinary prose",
    ],
)
def test_referenced_or_absent(line: str) -> None:
    assert not ct.unreferenced(line)


@pytest.mark.parametrize(
    "line",
    [
        f"# {T}: settle the numbers",
        f"{T} (#40): a reference after a space",
        f"a profile rule (#40). {T}",
        f"`{T}`",
        f"{T}(#1) and then a bare {T}",
        f"{T}(see #3)",
    ],
)
def test_unreferenced(line: str) -> None:
    assert ct.unreferenced(line)


@pytest.mark.parametrize(
    ("path", "skipped"),
    [
        ("docs/BLUEPRINT.md", True),
        ("sdk/CHANGELOG.md", True),
        ("app/web/node_modules/x/README.md", True),
        ("docs/adr/0021-ro-crate-is-a-record-not-a-message.md", False),
    ],
)
def test_excluded(path: str, skipped: bool) -> None:
    assert ct.excluded(path) is skipped


def test_the_repository_passes() -> None:
    assert ct.main() == 0

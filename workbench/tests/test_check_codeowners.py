"""The rules in scripts/check_codeowners.py: every path owned, no rule that matches nothing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_codeowners as cc  # noqa: E402

PATHS = ["README.md", "sdk/a.py", "docs/x/y.md", "agents/one/a.py", ".github/CODEOWNERS"]


@pytest.mark.parametrize(
    ("pattern", "path", "matches"),
    [
        ("/sdk/", "sdk/a.py", True),
        ("/sdk/", "other/sdk/a.py", False),
        ("sdk/", "other/sdk/a.py", True),
        ("*.md", "docs/x/y.md", True),
        ("/*.md", "docs/x/y.md", False),
        ("/*.md", "README.md", True),
        ("/docs/**/y.md", "docs/x/y.md", True),
        ("/docs", "docs/x/y.md", True),
    ],
)
def test_pattern(pattern: str, path: str, matches: bool) -> None:
    assert bool(cc.pattern_regex(pattern).match(path)) is matches


def test_covered_and_used() -> None:
    assert cc.problems("* @a\n/sdk/ @b\n", PATHS) == []


def test_unowned_path_is_reported() -> None:
    found = cc.problems("/sdk/ @a\n/docs/ @a\n", PATHS)
    assert "README.md: no owner" in found
    assert "sdk/a.py: no owner" not in found


def test_dead_rule_is_reported() -> None:
    found = cc.problems("* @a\n/gone/ @a\n", PATHS)
    assert found == [".github/CODEOWNERS:2: `/gone/` matches no tracked file"]


def test_later_rule_without_owner_unsets() -> None:
    assert "sdk/a.py: no owner" in cc.problems("* @a\n/sdk/\n", PATHS)


def test_comments_are_ignored() -> None:
    assert cc.problems("# note\n* @a # trailing\n", PATHS) == []

"""The size ratchet in scripts/check_size.py: files over the limit may only shrink."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_size as cs  # noqa: E402

LIMIT = cs.LIMITS[".py"]
MODULE = "harness/src/dd_harness/big.py"


@pytest.mark.parametrize(
    ("path", "checked"),
    [
        ("harness/src/dd_harness/conductor.py", True),
        ("agents/advisor-policy/src/dd_agent_advisor_policy/agent.py", True),
        ("app/web/src/components/conversation/ConversationHome.tsx", True),
        ("sdk/browser/src/card/card.ts", True),
        ("scripts/check_size.py", True),
        ("harness/tests/test_harness.py", False),
        ("scripts/tests/test_check_size.py", False),
        ("app/web/src/components/conversation/ConversationHome.test.tsx", False),
        ("app/web/e2e/shell.spec.ts", False),
        ("sdk/src/dd_sdk/schema/generated/core.py", False),
        ("docs/hooks.py", False),
        ("README.md", False),
    ],
)
def test_scope(path: str, checked: bool) -> None:
    assert cs.in_scope(path) is checked


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def _write(root: Path, relative: str, lines: int) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n" * lines, encoding="utf-8")
    subprocess.run(["git", "add", relative], cwd=root, check=True)


def _check(root: Path, *argv: str) -> int:
    return cs.main(list(argv), root=root, baseline_path=root / "baseline.toml")


def test_a_file_under_the_limit_passes(repo: Path) -> None:
    _write(repo, MODULE, LIMIT)
    assert _check(repo) == 0


def test_a_new_file_over_the_limit_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, MODULE, LIMIT + 1)
    assert _check(repo) == 1
    assert MODULE in capsys.readouterr().out


def test_a_recorded_file_may_not_grow(repo: Path) -> None:
    _write(repo, MODULE, LIMIT + 10)
    cs.write_baseline(repo / "baseline.toml", {MODULE: LIMIT + 10})
    assert _check(repo) == 0
    _write(repo, MODULE, LIMIT + 11)
    assert _check(repo) == 1


def test_update_lowers_an_entry_and_never_raises_one(repo: Path) -> None:
    baseline = repo / "baseline.toml"
    _write(repo, MODULE, LIMIT + 5)
    cs.write_baseline(baseline, {MODULE: LIMIT + 10})
    assert _check(repo) == 1  # The entry is slack: a file could regrow into it.
    assert _check(repo, "--update") == 0
    assert cs.load_baseline(baseline) == {MODULE: LIMIT + 5}
    _write(repo, MODULE, LIMIT + 8)
    assert _check(repo, "--update") == 1
    assert cs.load_baseline(baseline) == {MODULE: LIMIT + 5}


def test_a_stale_entry_is_reported_then_removed(repo: Path) -> None:
    baseline = repo / "baseline.toml"
    _write(repo, MODULE, LIMIT)
    cs.write_baseline(baseline, {MODULE: LIMIT + 10, "gone.py": 700})
    assert _check(repo) == 1
    assert _check(repo, "--update") == 0
    assert cs.load_baseline(baseline) == {}


def test_the_repository_passes() -> None:
    assert cs.problems(cs.oversize(ROOT), cs.load_baseline(cs.BASELINE)) == []

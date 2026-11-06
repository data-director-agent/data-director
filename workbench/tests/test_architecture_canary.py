"""Canaries for the architecture checks: plant each kind of violation, expect the check to fail.

A check that is misconfigured (a contract that names no package, a script that skips a directory)
passes on any code. So each test copies the repository's Python and configuration into a
temporary directory, shows that the copy passes, plants one known violation and shows that the
check now fails. The tests never touch the working tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_boundaries as cb  # noqa: E402

# A module of the harness, of an agent and of the SDK to plant a violation in.
HARNESS = "harness/src/dd_harness/__init__.py"
AGENT = "agents/example-hello/src/dd_agent_example_hello/__init__.py"
SDK = "sdk/src/dd_sdk/__init__.py"


def _tracked(*patterns: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", *patterns],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return [path for path in out.stdout.split("\0") if path]


@pytest.fixture
def copy(tmp_path: Path) -> Path:
    """The repository's Python files and `pyproject.toml` files, as a git repository."""
    for path in _tracked("*.py", "*pyproject.toml"):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, target)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    return tmp_path


def _plant(root: Path, relative: str, line: str) -> None:
    with (root / relative).open("a", encoding="utf-8") as file:
        file.write(f"\n{line}\n")


def _lint_imports(root: Path) -> subprocess.CompletedProcess[str]:
    """Import Linter over the copy, with the copy's packages ahead of the installed ones."""
    sources = [str(path.parent.parent) for path in root.glob("**/src/*/__init__.py")]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sources)}
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from importlinter.cli import lint_imports_command; lint_imports_command()",
            "--config",
            "pyproject.toml",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )


def test_the_copy_passes_both_checks(copy: Path) -> None:
    result = _lint_imports(copy)
    assert result.returncode == 0, result.stdout
    assert cb.problems(copy) == []


@pytest.mark.parametrize(
    ("relative", "line"),
    [
        (HARNESS, "import workbench"),  # the harness reaches up to a way in
        (SDK, "import dd_harness"),  # the sdk reaches up to the harness
        (AGENT, "import dd_agent_advisor_quality"),  # an agent reaches sideways to another
    ],
)
def test_import_linter_fails_on_a_direction_violation(copy: Path, relative: str, line: str) -> None:
    _plant(copy, relative, line)
    result = _lint_imports(copy)
    assert result.returncode != 0, result.stdout


def test_boundaries_fail_on_an_undeclared_import(copy: Path) -> None:
    _plant(copy, AGENT, "import dd_harness")
    report = cb.problems(copy)
    assert any(
        problem.startswith(AGENT) and "imports dd_harness" in problem for problem in report
    ), report


def test_boundaries_fail_on_a_read_outside_the_member(copy: Path) -> None:
    _plant(copy, AGENT, "from pathlib import Path\nOUT = Path(__file__).parents[9]")
    report = cb.problems(copy)
    assert any(problem.startswith(AGENT) and "reads outside" in problem for problem in report)

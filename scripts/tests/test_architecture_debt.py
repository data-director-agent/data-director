"""The debt count in scripts/architecture_debt.py, written to the CI job summary."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import architecture_debt as ad  # noqa: E402

PYPROJECT = """
[[tool.importlinter.contracts]]
name = "a"
type = "layers"
ignore_imports = ["x.a -> y.b", "x.c -> y.d"]

[[tool.importlinter.contracts]]
name = "b"
type = "forbidden"
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", relative], cwd=root, check=True)


def _by_what(root: Path) -> dict[str, int]:
    return {count.what: count.number for count in ad.counts(root)}


def test_each_kind_of_debt_is_counted(repo: Path) -> None:
    noqa = "# noqa"
    _write(
        repo,
        "pkg/src/m.py",
        f"def f():  {noqa}: C901, PLR0912\n    pass\n"
        f"def g(a, b):  {noqa}: PLR0913\n    pass\n"
        f"x = 1  {noqa}: E501\n",
    )
    _write(repo, "pkg/tests/test_m.py", f"def t():  {noqa}: C901\n    pass\n")
    disable = "eslint-disable-next-line"
    _write(repo, "web/src/A.tsx", f"// {disable} complexity -- debt\nexport function A() {{}}\n")
    _write(repo, "web/src/A.test.tsx", f"// {disable} complexity\n")
    _write(
        repo, "web/eslint.config.js", f"// a function over it carries an `{disable} complexity`\n"
    )
    _write(repo, "scripts/size_baseline.toml", '[[file]]\npath = "a"\nlines = 1\n')
    _write(
        repo,
        "scripts/boundaries.toml",
        '[[exception]]\npath = "a"\nproblem = "p"\n\n[[exception]]\npath = "b"\nproblem = "q"\n',
    )
    _write(repo, "pyproject.toml", PYPROJECT)

    found = _by_what(repo)

    assert found["Ruff complexity markers"] == 2
    assert found["ESLint complexity markers"] == 1
    assert found["Files over the size limit"] == 1
    assert found["Boundary exceptions"] == 2
    assert found["Import Linter exceptions"] == 2


def test_an_untracked_file_is_not_counted(repo: Path) -> None:
    (repo / "m.py").write_text("def f():  # noqa" + ": C901\n", encoding="utf-8")
    assert _by_what(repo)["Ruff complexity markers"] == 0


def test_missing_files_count_as_none(repo: Path) -> None:
    assert all(number == 0 for number in _by_what(repo).values())


def test_the_summary_is_appended_and_the_run_passes(repo: Path) -> None:
    summary = repo / "summary.md"
    summary.write_text("before\n", encoding="utf-8")

    assert ad.main(["--summary", str(summary)], root=repo) == 0

    text = summary.read_text(encoding="utf-8")
    assert text.startswith("before\n")
    assert "| Debt | Where | Count |" in text


def test_a_broken_file_does_not_fail_the_run(repo: Path) -> None:
    _write(repo, "pyproject.toml", "not = [valid")
    assert ad.main([], root=repo) == 0


def test_the_repository_itself_can_be_counted() -> None:
    assert ad.main([]) == 0

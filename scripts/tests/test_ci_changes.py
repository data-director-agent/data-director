"""Tests for scripts/ci_changes.sh --release: a version-bump-only release PR skips every job."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "ci_changes.sh"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def outputs(repo: Path, files: dict[str, tuple[str, str]], *flags: str) -> dict[str, str]:
    """Commit each file's old text, then its new text, and run the script on the change."""
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.org")
    git(repo, "config", "user.name", "t")
    for name, (old, _) in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(old)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    for name, (_, new) in files.items():
        (repo / name).write_text(new)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "change")
    paths = "\n".join(files) + "\n"
    done = subprocess.run(
        ["bash", str(SCRIPT), *flags],
        cwd=repo,
        input=paths,
        text=True,
        check=True,
        capture_output=True,
    )
    return dict(line.split("=", 1) for line in done.stdout.splitlines())


BUMP = {
    "sdk/pyproject.toml": (
        '[project]\nname = "x"\nversion = "0.1.0"\n',
        '[project]\nname = "x"\nversion = "0.2.0"\n',
    ),
    "sdk/CHANGELOG.md": ("# Changelog\n", "# Changelog\n\n## 0.2.0\n"),
    "uv.lock": (
        '[[package]]\nname = "x"\nversion = "0.1.0"\n',
        '[[package]]\nname = "x"\nversion = "0.2.0"\n',
    ),
}


def test_version_bump_skips_every_job(tmp_path: Path) -> None:
    out = outputs(tmp_path, BUMP, "--release")
    assert {k: v for k, v in out.items() if k != "codeql"} == dict.fromkeys(
        ["python", "web", "inventory", "deploy", "gateway", "docs"], "false"
    )
    assert out["codeql"] == "[]"


def test_source_change_on_the_branch_runs_jobs(tmp_path: Path) -> None:
    files = {**BUMP, "sdk/src/x.py": ("a = 1\n", "a = 2\n")}
    assert outputs(tmp_path, files, "--release")["python"] == "true"


def test_non_version_pyproject_change_runs_jobs(tmp_path: Path) -> None:
    files = {"sdk/pyproject.toml": ("dependencies = []\n", 'dependencies = ["y"]\n')}
    assert outputs(tmp_path, files, "--release")["python"] == "true"


@pytest.mark.parametrize("flags", [(), ("--all",)])
def test_without_release_a_lock_change_runs_everything(
    tmp_path: Path, flags: tuple[str, ...]
) -> None:
    out = outputs(tmp_path, BUMP, *flags)
    assert out["python"] == "true"
    assert out["gateway"] == "true"

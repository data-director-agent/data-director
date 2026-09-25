"""The local `.env` file fills unset variables and never replaces the real environment."""

from __future__ import annotations

from pathlib import Path

from workbench.settings import load_env_file


def _env_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_file_fills_an_unset_variable(tmp_path: Path) -> None:
    environ: dict[str, str] = {}
    assert load_env_file(_env_file(tmp_path, "DD_PRINCIPAL_NAME=J. Carberry\n"), environ)
    assert environ == {"DD_PRINCIPAL_NAME": "J. Carberry"}


def test_the_environment_wins(tmp_path: Path) -> None:
    environ = {"DD_PRINCIPAL_NAME": "Exported"}
    load_env_file(_env_file(tmp_path, "DD_PRINCIPAL_NAME=From file\n"), environ)
    assert environ == {"DD_PRINCIPAL_NAME": "Exported"}


def test_a_missing_file_changes_nothing(tmp_path: Path) -> None:
    environ = {"DD_RUNS_DIR": "runs"}
    assert not load_env_file(tmp_path / ".env", environ)
    assert environ == {"DD_RUNS_DIR": "runs"}


def test_a_key_without_a_value_is_skipped(tmp_path: Path) -> None:
    environ: dict[str, str] = {}
    load_env_file(_env_file(tmp_path, "DD_PRINCIPAL_ID\nDD_RUNS_DIR=runs\n"), environ)
    assert environ == {"DD_RUNS_DIR": "runs"}

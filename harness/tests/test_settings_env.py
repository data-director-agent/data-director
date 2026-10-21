"""The environment names the deployment's files, with the caller's defaults behind it
(ADR-0022); the local `.env` file fills unset variables and never replaces the real environment."""

from __future__ import annotations

from pathlib import Path

import pytest

from dd_harness.settings import Settings, SettingsError, build_conductor, load_env_file
from dd_harness.testing import PERMISSIVE, ScriptedAgent
from dd_sdk.contract.models import GroundingMode

PATH_VARIABLES = ("DD_RUNS_DIR", "DD_PROFILE", "DD_AGENTS_CONFIG", "DD_SOURCES_CONFIG")


@pytest.fixture
def no_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in PATH_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


def _defaults(tmp_path: Path) -> dict[str, Path]:
    return {
        "runs_dir": tmp_path / "runs",
        "profile": tmp_path / "profile.yaml",
        "agents_config": tmp_path / "agents.yaml",
        "sources_config": tmp_path / "sources.yaml",
    }


def test_the_harness_has_no_default_of_its_own(no_paths: None) -> None:
    with pytest.raises(SettingsError, match="DD_RUNS_DIR unset"):
        Settings.from_env()


def test_a_path_with_neither_variable_nor_default_is_named(no_paths: None, tmp_path: Path) -> None:
    defaults = _defaults(tmp_path)
    del defaults["sources_config"]
    with pytest.raises(SettingsError, match="DD_SOURCES_CONFIG unset"):
        Settings.from_env(**defaults)


def test_the_callers_defaults_fill_unset_paths(no_paths: None, tmp_path: Path) -> None:
    settings = Settings.from_env(**_defaults(tmp_path))
    assert settings.profile == tmp_path / "profile.yaml"
    assert settings.runs_dir == tmp_path / "runs"


def test_a_variable_wins_over_the_callers_default(
    no_paths: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DD_PROFILE", str(tmp_path / "deployed.yaml"))
    assert Settings.from_env(**_defaults(tmp_path)).profile == tmp_path / "deployed.yaml"


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


def test_the_caller_registers_in_process_agents_beside_the_list(
    no_paths: None, tmp_path: Path
) -> None:
    (tmp_path / "agents.yaml").write_text("agents: []\n", encoding="utf-8")
    (tmp_path / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    defaults = _defaults(tmp_path) | {"profile": PERMISSIVE}
    agent = ScriptedAgent(GroundingMode.NONE, RuntimeError("not run"))
    conductor = build_conductor(Settings.from_env(**defaults), agents=[agent])
    assert conductor.registry.ids() == ["fake.none"]

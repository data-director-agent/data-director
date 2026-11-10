"""The file backends pass the storage conformance kit (docs/specs/storage.md), and a storage
location names a backend this build has. The PostgreSQL backend's own tests are in
`test_postgres.py`."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from dd_harness.project_files import FileProjectLog
from dd_harness.projects import Projects, ProjectStore
from dd_harness.settings import (
    Settings,
    SettingsError,
    project_storage,
    projects_dir,
    redact_location,
    run_storage,
    storage_location,
)
from dd_harness.storage import ProjectLog, ProjectStorage, RunStorage
from dd_harness.store import RunStore
from dd_harness.testing import (
    PROJECT_LOG_CHECKS,
    PROJECT_STORAGE_CHECKS,
    RUN_STORAGE_CHECKS,
    check_project_rules,
    check_shared_record,
)


@pytest.mark.parametrize("check", RUN_STORAGE_CHECKS.values(), ids=RUN_STORAGE_CHECKS.keys())
def test_the_file_run_store_keeps_each_guarantee(
    tmp_path: Path, check: Callable[[Callable[[str], RunStorage]], None]
) -> None:
    check(lambda name: RunStore(tmp_path / name))


@pytest.mark.parametrize(
    "check", PROJECT_STORAGE_CHECKS.values(), ids=PROJECT_STORAGE_CHECKS.keys()
)
def test_the_file_project_store_keeps_each_guarantee(
    tmp_path: Path, check: Callable[[Callable[[str], ProjectStorage]], None]
) -> None:
    check(lambda name: ProjectStore(tmp_path / name))


@pytest.mark.parametrize("check", PROJECT_LOG_CHECKS.values(), ids=PROJECT_LOG_CHECKS.keys())
def test_the_file_project_log_keeps_each_guarantee(
    tmp_path: Path, check: Callable[[Callable[[str], ProjectLog]], None]
) -> None:
    check(lambda name: FileProjectLog(tmp_path / name))


def test_the_project_rules_keep_each_guarantee_over_a_log_that_only_stores(
    tmp_path: Path,
) -> None:
    """What a new backend runs: the rules, over its log, pass every `ProjectStorage` check."""
    check_project_rules(lambda name: FileProjectLog(tmp_path / name))
    assert isinstance(ProjectStore(tmp_path / "projects"), Projects)


def test_a_location_is_a_path_or_a_file_url(tmp_path: Path) -> None:
    assert storage_location(tmp_path) == tmp_path
    assert storage_location(str(tmp_path)) == tmp_path
    assert storage_location(tmp_path.as_uri()) == tmp_path
    assert storage_location(f"file://localhost{tmp_path}") == tmp_path
    assert isinstance(run_storage(tmp_path.as_uri()), RunStore)
    assert isinstance(project_storage(str(tmp_path / "projects")), ProjectStore)


@pytest.mark.parametrize("location", ["mongodb://db.example/runs", "s3://bucket/runs"])
def test_a_location_naming_another_backend_is_refused_with_those_supported(
    location: str, tmp_path: Path
) -> None:
    with pytest.raises(SettingsError, match=r"not supported by this build.*file://.*postgresql://"):
        run_storage(location)
    with pytest.raises(SettingsError, match="not supported"):
        project_storage(location)
    assert not any(tmp_path.iterdir())


def test_a_database_location_is_kept_as_given() -> None:
    location = "postgresql://db.example:5433/dd?sslmode=require"
    assert storage_location(location) == location


@pytest.mark.parametrize(
    "location",
    [
        "postgresql://someone:hunter2@db.example/dd",
        "postgresql://someone@db.example/dd?password=hunter2",
        "postgresql://db.example/dd?sslmode=require&PASSWORD=hunter2",
    ],
)
def test_a_database_location_carrying_a_password_is_refused_without_showing_it(
    location: str,
) -> None:
    with pytest.raises(SettingsError, match="password") as refused:
        storage_location(location, "DD_RUNS_DIR")
    assert "hunter2" not in str(refused.value)
    assert "DD_RUNS_DIR" in str(refused.value)


def test_a_location_is_shown_without_its_user_or_parameters(tmp_path: Path) -> None:
    assert redact_location("postgresql://someone@db.example:5433/dd?sslmode=require") == (
        "postgresql://db.example:5433/dd"
    )
    assert redact_location("postgresql://[::1]/dd") == "postgresql://[::1]/dd"
    # No host: libpq takes it from PGHOST (the Compose stack's `postgres` profile).
    assert redact_location("postgresql://dd@/dd") == "postgresql:///dd"
    assert redact_location(tmp_path) == str(tmp_path)


def test_a_database_location_without_its_driver_names_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "dd_harness.postgres", None)  # as if psycopg were missing
    with pytest.raises(SettingsError, match=r"DD_RUNS_DIR: .*data-director-harness\[postgres\]"):
        run_storage("postgresql://db.example/dd")
    with pytest.raises(SettingsError, match=r"DD_PROJECTS_DIR: .*\[postgres\]"):
        project_storage("postgresql://db.example/dd")


def test_a_directory_that_cannot_be_made_stops_start_up(tmp_path: Path) -> None:
    (tmp_path / "file").write_text("not a directory")
    with pytest.raises(SettingsError, match=r"DD_RUNS_DIR .* cannot be used"):
        run_storage(tmp_path / "file" / "runs")
    with pytest.raises(SettingsError, match=r"DD_PROJECTS_DIR .* cannot be used"):
        project_storage(tmp_path / "file" / "projects")


def test_a_file_url_with_a_host_is_refused() -> None:
    with pytest.raises(SettingsError, match="names no host"):
        storage_location("file://elsewhere/runs")


def test_the_variables_take_a_file_url_or_a_database_and_refuse_another_scheme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DD_PROJECTS_DIR", (tmp_path / "projects").as_uri())
    assert projects_dir() == tmp_path / "projects"
    monkeypatch.setenv("DD_RUNS_DIR", (tmp_path / "runs").as_uri())
    given = {"profile": tmp_path, "agents_config": tmp_path, "sources_config": tmp_path}
    assert Settings.from_env(**given).runs_dir == tmp_path / "runs"
    monkeypatch.setenv("DD_RUNS_DIR", "mongodb://db.example/runs")
    with pytest.raises(SettingsError, match="DD_RUNS_DIR: mongodb:// storage"):
        Settings.from_env(**given)
    monkeypatch.setenv("DD_RUNS_DIR", "postgresql://db.example/dd")
    assert Settings.from_env(**given).runs_dir == "postgresql://db.example/dd"
    monkeypatch.setenv("DD_PROJECTS_DIR", "postgresql://db.example/dd")
    assert projects_dir() == "postgresql://db.example/dd"
    monkeypatch.setenv("DD_PROJECTS_DIR", "postgresql://someone:hunter2@db.example/dd")
    with pytest.raises(SettingsError, match=r"DD_PROJECTS_DIR: .* carries a password"):
        projects_dir()


def test_only_a_database_shares_a_section_between_stores(tmp_path: Path) -> None:
    """The file backend's lock holds within one instance, so two logs over one directory do not
    exclude each other; `check_shared_record` is for a backend that serves several instances
    (harness/tests/test_postgres.py)."""
    with pytest.raises(AssertionError):
        check_shared_record(lambda name: FileProjectLog(tmp_path / name))

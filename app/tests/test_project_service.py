"""The app's own rules about project requests, held by `ProjectService` rather than by a route,
and tested here without a server (docs/specs/projects.md, docs/specs/deposit.md)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from support import ORDA, configure_env, new_governance, pin_export

from dd_app.governance import Governance
from dd_app.project_service import (
    ProjectService,
    RepositoriesUnavailableError,
    TitleMismatchError,
)
from dd_harness.projects import PROJECT_DELETED, UnknownProjectError
from dd_harness.testing import TEST_PRINCIPAL


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DD_SOURCES_CONFIG", str(pin_export(tmp_path / "re3data")))
    yield from new_governance()


@pytest.fixture
def service(governance: Governance) -> ProjectService:
    return ProjectService.over(governance)


def test_a_project_is_deleted_only_by_its_name(service: ProjectService) -> None:
    project = service.lifecycle.create("Soil cores", acted_for=TEST_PRINCIPAL)["project_id"]
    with pytest.raises(TitleMismatchError):
        service.lifecycle.delete(project, "Soil", acted_for=TEST_PRINCIPAL, caused_by="test")
    assert service.lifecycle.governance.is_deleted(project) is False

    deleted = service.lifecycle.delete(
        project, "  Soil cores ", acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    assert deleted["deleted"] is not None
    assert service.lifecycle.governance.projects is not None
    assert service.lifecycle.governance.projects.events(project)[-1]["event"] == PROJECT_DELETED


def test_a_project_with_no_title_is_deleted_by_its_identifier(service: ProjectService) -> None:
    project = service.lifecycle.create(None, acted_for=TEST_PRINCIPAL)["project_id"]
    with pytest.raises(TitleMismatchError):
        service.lifecycle.delete(project, "", acted_for=TEST_PRINCIPAL, caused_by="test")
    service.lifecycle.delete(project, project, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert service.lifecycle.governance.is_deleted(project) is True


def test_a_repository_choice_resolves_against_the_pinned_export(service: ProjectService) -> None:
    project = service.lifecycle.create(None, acted_for=TEST_PRINCIPAL)["project_id"]
    chosen = service.deposit.choose_repository(
        project, ORDA, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    assert chosen is not None
    assert chosen == service.deposit.requirements(project)


def test_no_repository_is_chosen_without_requirement_sets(service: ProjectService) -> None:
    project = service.lifecycle.create(None, acted_for=TEST_PRINCIPAL)["project_id"]
    service.lifecycle.governance.requirements = None
    with pytest.raises(RepositoriesUnavailableError):
        service.deposit.choose_repository(project, ORDA, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert service.deposit.requirements(project) is None


def test_a_server_that_keeps_no_projects_knows_none(service: ProjectService) -> None:
    service.lifecycle.governance.projects = None
    assert service.lifecycle.keeps_projects is False
    with pytest.raises(UnknownProjectError):
        service.progress.progress("01900000-0000-7000-8000-000000000001")

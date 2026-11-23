"""A data steward's reads and actions in another person's project, and the profile that gives
people their deployment roles, are security events as well as project events
(docs/specs/stewardship.md, Non-functional requirements; docs/specs/security.md, Security
events; #154).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from test_escalations import COLLEAGUE, STEWARD, open_one
from test_steward_interventions import LIBRARY_ONLY, act

from dd_harness.projects import ProjectStore, StewardRefusedError, UnknownProjectError
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk import security_log
from dd_sdk.security_log import SecurityEvent
from dd_sdk.testing import security_events


@pytest.fixture
def events(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.INFO, logger=security_log.LOGGER)
    return caplog


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project_id(projects: ProjectStore) -> str:
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    projects.add_member(
        project_id, COLLEAGUE.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    open_one(projects, project_id, LIBRARY_ONLY, team_id="library-rdm")
    return project_id


def recorded(caplog: pytest.LogCaptureFixture, event: SecurityEvent) -> list[dict[str, Any]]:
    return [e for e in security_events(caplog.records) if e["event"] == event]


def test_a_stewards_read_is_a_security_event_once_a_day(
    projects: ProjectStore, project_id: str, events: pytest.LogCaptureFixture
) -> None:
    for _ in range(3):
        act(projects, project_id, "read", STEWARD, LIBRARY_ONLY)
    (viewed,) = recorded(events, SecurityEvent.STEWARD_VIEWED)
    assert viewed["principal"] == STEWARD.principal_id
    assert viewed["project_id"] == project_id
    assert viewed["outcome"] == "success"


@pytest.mark.parametrize("action", ["message", "pause", "clear_gate", "refuse_gate"])
def test_each_stewards_action_is_a_security_event_naming_it(
    projects: ProjectStore, project_id: str, events: pytest.LogCaptureFixture, action: str
) -> None:
    act(projects, project_id, action, STEWARD, LIBRARY_ONLY)
    (acted,) = recorded(events, SecurityEvent.STEWARD_ACTED)
    assert acted["principal"] == STEWARD.principal_id
    assert acted["project_id"] == project_id
    assert acted["action"] == action


def test_lifting_a_pause_is_a_security_event(
    projects: ProjectStore, project_id: str, events: pytest.LogCaptureFixture
) -> None:
    act(projects, project_id, "pause", STEWARD, LIBRARY_ONLY)
    act(projects, project_id, "resume", STEWARD, LIBRARY_ONLY)
    actions = [e["action"] for e in recorded(events, SecurityEvent.STEWARD_ACTED)]
    assert actions == ["pause", "resume"]


def test_a_stewards_note_never_reaches_the_security_log(
    projects: ProjectStore, project_id: str, events: pytest.LogCaptureFixture
) -> None:
    note = "A note"
    act(projects, project_id, "message", STEWARD, LIBRARY_ONLY)
    assert recorded(events, SecurityEvent.STEWARD_ACTED)
    for record in security_events(events.records):
        assert note not in json.dumps(record)


def test_a_refused_action_and_a_members_read_are_not_steward_events(
    projects: ProjectStore, project_id: str, events: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(StewardRefusedError):
        act(projects, project_id, "message", COLLEAGUE, LIBRARY_ONLY)
    with pytest.raises(UnknownProjectError):
        act(projects, project_id, "read", COLLEAGUE, LIBRARY_ONLY)
    assert recorded(events, SecurityEvent.STEWARD_ACTED) == []
    assert recorded(events, SecurityEvent.STEWARD_VIEWED) == []


def test_loading_a_profile_records_its_identifier_and_version(
    events: pytest.LogCaptureFixture,
) -> None:
    LIBRARY_ONLY.record_loaded("harness")
    (loaded,) = recorded(events, SecurityEvent.PROFILE_LOADED)
    assert loaded["profile_id"] == LIBRARY_ONLY.profile_id
    assert loaded["profile_version"] == LIBRARY_ONLY.version
    assert loaded["service"] == "harness"

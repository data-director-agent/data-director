"""Telling people that an escalation has moved, through the app's server
(docs/specs/stewardship.md, invariant 13; #378): a researcher's moves are sent to the team's
address, a steward's moves are read by the project's researchers at `GET /api/notices`, and a
profile that names a team address with no mail server stops start-up. The signed-in person is
`TEST_PRINCIPAL`; `OTHER` is a steward of the library team."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from starlette.testclient import TestClient
from support import (
    APP_URL,
    JSON_HEADERS,
    OTHER,
    check_fixture,
    configure_env,
    dist_dir,
    new_governance,
)

from dd_app.app import build_app
from dd_app.config import EXAMPLE_PROFILE, settings_from_env
from dd_app.governance import CREATED_BY_ROUTE, Governance
from dd_app.routes.escalations import Notices
from dd_harness.testing import TEST_PRINCIPAL
from dd_harness.testing.notifications import RecordingNotifier
from dd_sdk.credentials import ConfigError

ADDRESS = "rdm@example.ac.uk"
NOTE = "Can I share the interview transcripts?"
LIBRARY = {
    "id": "library-rdm",
    "name": "Library Research Data Team",
    "members": [OTHER.principal_id],
    "notify": ADDRESS,
}
FIXED = "2026-01-01T00:00:00+00:00"


def with_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, team: dict[str, Any]) -> None:
    body = yaml.safe_load(EXAMPLE_PROFILE.read_text())
    body["stewardship"] = {"teams": [team]}
    profile = tmp_path / "profile.yaml"
    profile.write_text(yaml.safe_dump(body))
    monkeypatch.setenv("DD_PROFILE", str(profile))


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def governance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, notifier: RecordingNotifier
) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    with_profile(monkeypatch, tmp_path, LIBRARY)
    monkeypatch.setenv("DD_SMTP_URL", "smtp://mail.example.ac.uk")
    monkeypatch.setenv("DD_MAIL_FROM", "data-director@example.ac.uk")
    for found in new_governance():
        # The mail server the environment names is replaced by one that keeps what it is sent.
        yield dataclasses.replace(found, notifier=notifier)


@pytest.fixture
def client(governance: Governance, tmp_path: Path) -> TestClient:
    return TestClient(build_app(governance, dist_dir(tmp_path)))


@pytest.fixture
def owned(governance: Governance) -> str:
    assert governance.projects is not None
    return governance.projects.create(
        acted_for=TEST_PRINCIPAL, caused_by=CREATED_BY_ROUTE, title="Peat"
    )


def test_a_researchers_moves_are_sent_to_the_teams_address_without_the_note(
    client: TestClient, notifier: RecordingNotifier, owned: str
) -> None:
    sent = client.post(
        f"/api/projects/{owned}/escalations",
        json={"note": NOTE, "scope_shared": ["The project's title"]},
        headers=JSON_HEADERS,
    )
    assert sent.status_code == 201
    (escalation,) = sent.json()["escalations"]
    url = f"/api/projects/{owned}/escalations/{escalation['escalation_id']}"
    assert client.post(url, json={"move": "withdraw"}, headers=JSON_HEADERS).status_code == 200
    assert [(address, notice.kind) for address, notice in notifier.sent] == [
        (ADDRESS, "opened"),
        (ADDRESS, "withdrawn"),
    ]
    assert all(NOTE not in notice.subject for _, notice in notifier.sent)
    assert all("Peat" not in notice.subject for _, notice in notifier.sent)


def test_a_researcher_reads_what_a_steward_did_in_their_project(
    client: TestClient, governance: Governance, owned: str
) -> None:
    store = governance.projects
    assert store is not None
    escalation_id = client.post(
        f"/api/projects/{owned}/escalations", json={"note": NOTE}, headers=JSON_HEADERS
    ).json()["escalations"][0]["escalation_id"]
    store.move_escalation(
        owned, escalation_id, "take", side="steward", acted_for=OTHER, caused_by="test"
    )
    store.move_escalation(
        owned,
        escalation_id,
        "wait",
        side="steward",
        note="Which consent form?",
        acted_for=OTHER,
        caused_by="test",
    )
    found = client.get("/api/notices")
    assert found.status_code == 200
    (notice,) = found.json()["notices"]
    assert (notice["kind"], notice["project_id"]) == ("waiting", owned)
    assert notice["path"] == f"/projects/{owned}"
    check_fixture(
        "notices.json",
        {
            "notices": [
                {
                    **notice,
                    "project_id": "019a0000-0000-7000-8000-0000000000a1",
                    "event_id": "019a0000-0000-7000-8000-0000000000b1",
                    "escalation_id": "019a0000-0000-7000-8000-0000000000e1",
                    "path": "/projects/019a0000-0000-7000-8000-0000000000a1",
                    "at": FIXED,
                }
            ]
        },
        model=Notices,
    )


def test_a_team_address_with_no_mail_server_stops_start_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure_env(monkeypatch, tmp_path)
    with_profile(monkeypatch, tmp_path, LIBRARY)
    monkeypatch.delenv("DD_SMTP_URL", raising=False)
    with pytest.raises(ConfigError):
        Governance.create(settings_from_env(), APP_URL)

"""Telling people that an escalation has moved (docs/specs/stewardship.md, invariant 13; #378).

A steward team is emailed at the address the profile names, for the notices it chose; the
project's researchers read theirs in the app. A notice holds a subject and a link, never the note
or the project's title. An escalation nobody takes within `reroute_after` is sent to its team
again by the sweep, once for each time it was routed.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from dd_harness import escalation_api, mail, notifications
from dd_harness.escalation_api import Confirmed, Requested
from dd_harness.policy import PolicyError, Profile
from dd_harness.projects import ESCALATION_REROUTED, ProjectStore
from dd_harness.stewardship import TEAM_NOTICES
from dd_harness.testing import PERMISSIVE, TEST_PRINCIPAL
from dd_harness.testing.notifications import RecordingNotifier
from dd_sdk.contract.models import Principal, PrincipalKind, now
from dd_sdk.credentials import ConfigError

STEWARD = Principal(principal_id="https://orcid.org/0000-0001-5000-0007", name="A Steward")
STRANGER = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="A Stranger")
NOTE = "The consent forms mention a named participant, Ada Example"
TITLE = "Interviews with coastal communities"
ADDRESS = "rdm@example.ac.uk"


def library(**extra: Any) -> dict[str, Any]:
    return {
        "id": "library-rdm",
        "name": "Library Research Data Team",
        "members": [STEWARD.principal_id],
        **extra,
    }


def profile(team: dict[str, Any] | None = None, **stewardship: Any) -> Profile:
    data = yaml.safe_load(PERMISSIVE.read_text())
    data["stewardship"] = {"teams": [team or library(notify=ADDRESS)], **stewardship}
    return Profile.from_mapping(data, source="test", digest="0" * 64)


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project_id(projects: ProjectStore) -> str:
    return projects.create(title=TITLE, acted_for=TEST_PRINCIPAL, caused_by="test")


def open_one(projects: ProjectStore, deployment: Profile, project_id: str) -> dict[str, Any]:
    return escalation_api.open_escalation(
        projects,
        deployment,
        project_id,
        Confirmed(origin={"kind": "researcher"}, note=NOTE),
        lambda _: None,
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )


def move(
    projects: ProjectStore,
    deployment: Profile,
    project_id: str,
    escalation_id: str,
    name: str,
    *,
    as_steward: bool,
) -> dict[str, Any]:
    return escalation_api.move(
        projects,
        deployment,
        project_id,
        Requested(escalation_id, name, NOTE),
        as_steward=as_steward,
        acted_for=STEWARD if as_steward else TEST_PRINCIPAL,
        caused_by="test",
    )


def tell(
    projects: ProjectStore, deployment: Profile, project_id: str, escalation: dict[str, Any]
) -> RecordingNotifier:
    notifier = RecordingNotifier()
    escalation_api.tell_team(notifier, projects, deployment, project_id, escalation)
    return notifier


def assert_no_content(notice: notifications.Notice) -> None:
    for text in (NOTE, TITLE, STEWARD.name, TEST_PRINCIPAL.name):
        assert text not in notice.subject
        assert text not in notice.path


# --- The profile's keys ---------------------------------------------------------------------


def test_a_team_names_its_address_and_what_it_is_told_and_the_profile_when_to_send_again() -> None:
    deployment = profile(library(notify=ADDRESS, notify_on=["opened"]), reroute_after="P2D")
    (team,) = deployment.stewardship.teams
    assert team.notify == ADDRESS
    assert team.notify_on == {"opened"}
    assert deployment.stewardship.reroute_after == timedelta(days=2)
    assert profile(library()).stewardship.teams[0].notify_on == set(TEAM_NOTICES)


@pytest.mark.parametrize(
    ("team", "stewardship"),
    [
        (library(notify="not an address"), {}),
        (library(notify=ADDRESS, notify_on=["everything"]), {}),
        (library(notify=ADDRESS, notify_on="opened"), {}),
        (library(notify=ADDRESS), {"reroute_after": "3 days"}),
        (library(notify=ADDRESS), {"reroute_after": "PT30M"}),
    ],
)
def test_a_malformed_address_notice_or_duration_is_refused_at_load(
    team: dict[str, Any], stewardship: dict[str, Any]
) -> None:
    with pytest.raises(PolicyError):
        profile(team, **stewardship)


# --- Whom a move tells ----------------------------------------------------------------------


def test_opening_an_escalation_tells_its_team_with_a_subject_and_a_link_only(
    projects: ProjectStore, project_id: str
) -> None:
    deployment = profile()
    opened = open_one(projects, deployment, project_id)
    ((address, notice),) = tell(projects, deployment, project_id, opened).sent
    assert address == ADDRESS
    assert (notice.audience, notice.kind) == ("team", "opened")
    assert notice.team_id == "library-rdm"
    assert notice.escalation_id == opened["escalation_id"]
    assert notice.path == notifications.STEWARD_QUEUE_PATH
    assert_no_content(notice)


def test_a_researchers_moves_tell_the_team_and_a_stewards_moves_do_not(
    projects: ProjectStore, project_id: str
) -> None:
    deployment = profile()
    escalation_id = open_one(projects, deployment, project_id)["escalation_id"]
    told = []
    for name, as_steward in (
        ("take", True),
        ("wait", True),
        ("reply", False),
        ("resolve", True),
        ("reopen", False),
        ("withdraw", False),
    ):
        moved = move(projects, deployment, project_id, escalation_id, name, as_steward=as_steward)
        told += [notice.kind for _, notice in tell(projects, deployment, project_id, moved).sent]
    assert told == ["replied", "reopened", "withdrawn"]


def test_a_team_is_told_only_what_it_chose_and_nothing_without_an_address(
    projects: ProjectStore, project_id: str
) -> None:
    chosen = profile(library(notify=ADDRESS, notify_on=["withdrawn"]))
    opened = open_one(projects, chosen, project_id)
    assert tell(projects, chosen, project_id, opened).sent == []
    withdrawn = move(
        projects, chosen, project_id, opened["escalation_id"], "withdraw", as_steward=False
    )
    assert [n.kind for _, n in tell(projects, chosen, project_id, withdrawn).sent] == ["withdrawn"]
    silent = profile(library())
    again = open_one(projects, silent, project_id)
    assert tell(projects, silent, project_id, again).sent == []


def test_a_researcher_reads_what_stewards_did_in_their_projects_and_nobody_else_does(
    projects: ProjectStore, project_id: str
) -> None:
    deployment = profile()
    escalation_id = open_one(projects, deployment, project_id)["escalation_id"]
    move(projects, deployment, project_id, escalation_id, "take", as_steward=True)
    move(projects, deployment, project_id, escalation_id, "wait", as_steward=True)
    projects.steward_message(project_id, NOTE, acted_for=STEWARD, caused_by="test")
    since = now() - timedelta(days=1)
    found = notifications.for_person(projects, deployment, TEST_PRINCIPAL, since=since)
    assert {notice["kind"] for notice in found} == {"waiting", "message"}
    assert all(notice["path"] == f"/projects/{project_id}" for notice in found)
    assert all(NOTE not in notice["subject"] for notice in found)
    assert found == sorted(found, key=lambda notice: notice["at"], reverse=True)
    assert notifications.for_person(projects, deployment, STRANGER, since=since) == []
    later = now() + timedelta(days=1)
    assert notifications.for_person(projects, deployment, TEST_PRINCIPAL, since=later) == []


# --- Sending an escalation again ------------------------------------------------------------


def test_the_sweep_sends_an_escalation_nobody_took_to_its_team_again_once(
    projects: ProjectStore, project_id: str
) -> None:
    deployment = profile(reroute_after="P1D")
    escalation_id = open_one(projects, deployment, project_id)["escalation_id"]
    notifier = RecordingNotifier()
    assert escalation_api.sweep(projects, deployment, notifier, now=now()) == []
    later = now() + timedelta(days=2)
    (sent,) = escalation_api.sweep(projects, deployment, notifier, now=later)
    assert (sent["escalation_id"], sent["state"]) == (escalation_id, "open")
    assert [notice.kind for _, notice in notifier.sent] == ["rerouted"]
    # Sent again just now, so not due again until a day after that.
    soon = now() + timedelta(hours=12)
    assert escalation_api.sweep(projects, deployment, notifier, now=soon) == []
    (rerouted,) = [e for e in projects.events(project_id) if e["event"] == ESCALATION_REROUTED]
    assert rerouted["acted_for"]["principal_kind"] == PrincipalKind.ACCOUNTABLE_ROLE.value
    found = notifications.for_person(
        projects, deployment, TEST_PRINCIPAL, since=now() - timedelta(days=1)
    )
    assert [notice["kind"] for notice in found] == ["rerouted"]


def test_the_sweep_leaves_a_taken_escalation_and_a_profile_without_reroute_after(
    projects: ProjectStore, project_id: str
) -> None:
    deployment = profile(reroute_after="PT1H")
    escalation_id = open_one(projects, deployment, project_id)["escalation_id"]
    later = now() + timedelta(days=30)
    assert escalation_api.sweep(projects, profile(), RecordingNotifier(), now=later) == []
    move(projects, deployment, project_id, escalation_id, "take", as_steward=True)
    assert escalation_api.sweep(projects, deployment, RecordingNotifier(), now=later) == []


def test_releasing_an_escalation_routes_it_afresh(projects: ProjectStore, project_id: str) -> None:
    deployment = profile(reroute_after="P1D")
    escalation_id = open_one(projects, deployment, project_id)["escalation_id"]
    move(projects, deployment, project_id, escalation_id, "take", as_steward=True)
    released = move(projects, deployment, project_id, escalation_id, "release", as_steward=True)
    assert released["routed_at"] == released["updated_at"]
    assert released["routed_at"] > released["opened_at"]


# --- Email ----------------------------------------------------------------------------------

ENV = {
    "DD_SMTP_URL": "smtp://mail.example.ac.uk",
    "DD_MAIL_FROM": "data-director@example.ac.uk",
    "DD_APP_PUBLIC_URL": "https://dd.example.ac.uk/",
}


class FakeSmtp:
    """Records what an SMTP session was asked to do; fails on `send_message` when told to."""

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.fail = fail

    def __call__(self, host: str, port: int, timeout: float) -> FakeSmtp:
        self.calls.append(("connect", (host, port)))
        return self

    def quit(self) -> None:
        self.calls.append(("quit", None))

    def starttls(self) -> None:
        self.calls.append(("starttls", None))

    def login(self, user: str, password: str) -> None:
        self.calls.append(("login", user))

    def send_message(self, message: Any) -> None:
        if self.fail:
            raise smtplib.SMTPServerDisconnected("gone")
        self.calls.append(("send", message))


def a_notice() -> notifications.Notice:
    return notifications.Notice(
        audience="team",
        kind="opened",
        project_id="019a0000-0000-7000-8000-000000000002",
        event_id="019a0000-0000-7000-8000-000000000003",
        at=now().isoformat(),
        subject="A new request for Library Research Data Team",
        path=notifications.STEWARD_QUEUE_PATH,
        team_id="library-rdm",
    )


def test_a_notice_is_emailed_over_starttls_with_a_link_to_the_app() -> None:
    settings = mail.settings_from_env({**ENV, "DD_SMTP_USERNAME": "dd", "DD_SMTP_PASSWORD": "pw"})
    assert settings is not None and (settings.port, settings.tls) == (587, False)
    smtp = FakeSmtp()
    mail.SmtpNotifier(settings, background=False, connect=smtp).send(ADDRESS, a_notice())
    assert [name for name, _ in smtp.calls] == ["connect", "starttls", "login", "send", "quit"]
    sent = smtp.calls[-2][1]
    assert sent["To"] == ADDRESS
    assert "https://dd.example.ac.uk/steward" in sent.get_content()


def test_a_queued_notice_is_sent_off_the_callers_thread() -> None:
    settings = mail.settings_from_env({**ENV, "DD_SMTP_URL": "smtps://mail.example.ac.uk"})
    assert settings is not None and (settings.port, settings.tls) == (465, True)
    smtp = FakeSmtp()
    notifier = mail.SmtpNotifier(settings, connect=smtp)
    notifier.send(ADDRESS, a_notice())
    notifier.flush()
    assert [name for name, _ in smtp.calls] == ["connect", "send", "quit"]


def test_a_notice_that_cannot_be_sent_is_logged_and_changes_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = mail.settings_from_env(ENV)
    assert settings is not None
    notifier = mail.SmtpNotifier(settings, background=False, connect=FakeSmtp(fail=True))
    with caplog.at_level(logging.WARNING, logger="dd_harness.mail"):
        notifier.send(ADDRESS, a_notice())
    assert any(a_notice().event_id in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    "env",
    [
        {**ENV, "DD_SMTP_URL": "http://mail.example.ac.uk"},
        {**ENV, "DD_SMTP_URL": "smtp://user:secret@mail.example.ac.uk"},
        {k: v for k, v in ENV.items() if k != "DD_MAIL_FROM"},
        {k: v for k, v in ENV.items() if k != "DD_APP_PUBLIC_URL"},
    ],
)
def test_unusable_mail_settings_stop_start_up(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        mail.settings_from_env(env)


def test_a_team_address_with_no_mail_server_stops_start_up() -> None:
    with pytest.raises(ConfigError):
        mail.notifier_for(profile(), {})
    assert mail.notifier_for(profile(library()), {}) is notifications.NULL_NOTIFIER
    assert isinstance(mail.notifier_for(profile(), ENV), mail.SmtpNotifier)

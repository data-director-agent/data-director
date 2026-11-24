"""The admin service's Security page (docs/guide/operations/admin.md): the security records in the
units' journal, filtered by event, outcome and service. A line that only looks like a record is
cut to the fields a record has, and a journal that cannot be read is named."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from dd_admin import security_events
from dd_admin.app import Admin, build_app
from dd_admin.settings import AdminSettings
from dd_admin.system import Done, System

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def record(
    event: str, outcome: str = "success", service: str = "app", **extra: object
) -> dict[str, object]:
    return {
        "time": "2026-11-24T11:00:00.000Z",
        "event": event,
        "outcome": outcome,
        "service": service,
        "principal": "https://orcid.org/0000-0002-1825-0097",
        "reason": None,
        **extra,
    }


def journal(*messages: str) -> str:
    return "\n".join(
        json.dumps(
            {
                "MESSAGE": message,
                "__REALTIME_TIMESTAMP": str(int(NOW.timestamp() * 1_000_000)),
                "_SYSTEMD_UNIT": "data-director-app.service",
            }
        )
        for message in messages
    )


def line(**fields: object) -> str:
    return json.dumps(fields, separators=(",", ":"))


RECORDS = (
    line(**record("sign-in.succeeded")),
    line(**record("sign-in.failed", "failure", reason="not-admitted")),
    line(
        **record("grant.minted", service="harness", agent_id="advisor.policy", models=["m1", "m2"])
    ),
    "an ordinary log line",
    '{"not": "a security record"}',
)


@dataclass
class FakeSystem(System):
    """`journalctl` as it answers; `searches` False for a machine whose journalctl cannot --grep."""

    text: str = field(default_factory=lambda: journal(*RECORDS))
    searches: bool = True
    status: int = 0
    commands: list[tuple[str, ...]] = field(default_factory=list)

    def run(self, *cmd: str, timeout_s: float = 60.0) -> Done:
        self.commands.append(cmd)
        if self.status:
            return Done(self.status, "", "Failed to open journal: permission denied")
        if "--grep" in cmd and not self.searches:
            return Done(1, "", "Compiled without pattern matching support")
        return Done(0, self.text)


def open_client(system: FakeSystem, systemd: bool = True) -> TestClient:
    admin = Admin.open(AdminSettings(systemd=systemd), system)
    return TestClient(build_app(admin), base_url="http://localhost:8200")


def main(page: str) -> str:
    return page.split("<main", 1)[1]


def table(page: str) -> str:
    """The events listed, not the filters' options, which name every event there is."""
    return page.split("<h2>Events</h2>", 1)[1]


def test_the_page_answers_get_and_nothing_that_could_change_state() -> None:
    http = open_client(FakeSystem())
    assert http.get("/security").status_code == 200
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert http.request(method, "/security").status_code == 405


def test_records_are_listed_and_other_lines_are_not() -> None:
    page = main(open_client(FakeSystem()).get("/security").text)
    for shown in ("sign-in.succeeded", "sign-in.failed", "not-admitted", "grant.minted"):
        assert shown in page
    assert "advisor.policy" in page and "m1, m2" in page
    assert "ordinary log line" not in page and "security record" not in page


def test_the_filters_narrow_the_list() -> None:
    http = open_client(FakeSystem())
    failed = table(http.get("/security", params={"outcome": "failure"}).text)
    assert "sign-in.failed" in failed and "grant.minted" not in failed
    by_service = table(http.get("/security", params={"service": "harness"}).text)
    assert "grant.minted" in by_service and "sign-in.failed" not in by_service
    none = table(http.get("/security", params={"event": "grant.minted", "outcome": "failure"}).text)
    assert "No security event matches" in none


def test_a_window_the_page_does_not_offer_is_the_default() -> None:
    system = FakeSystem()
    open_client(system).get("/security", params={"days": "9999"})
    assert system.commands and str(int((NOW - timedelta(days=1)).timestamp()))[:4] in " ".join(
        system.commands[0]
    )
    assert security_events.read(AdminSettings(systemd=True), system, 7, NOW).days == 7


def test_without_the_journal_setting_it_names_it_and_runs_nothing() -> None:
    system = FakeSystem()
    page = open_client(system, systemd=False).get("/security").text
    assert "DD_ADMIN_SYSTEMD" in page and system.commands == []


def test_a_journal_that_cannot_be_read_is_named() -> None:
    page = open_client(FakeSystem(status=1)).get("/security").text
    assert "cannot be read" in page and "permission denied" in page


def test_a_journalctl_that_cannot_search_is_read_whole_and_says_so() -> None:
    system = FakeSystem(searches=False)
    found = security_events.read(AdminSettings(systemd=True), system, now=NOW)
    assert not found.searched and len(found.entries) == 3
    assert "could not search" in open_client(FakeSystem(searches=False)).get("/security").text


# --- What a line may carry -----------------------------------------------------------------------


def test_only_the_fields_a_record_defines_are_kept_and_each_is_cut() -> None:
    forged = line(**record("sign-in.failed", "failure", password="hunter2", reason="x" * 1000))
    found = security_events.parse(journal(forged))
    assert len(found) == 1 and len(found[0].reason) == security_events.FIELD_LENGTH
    assert "hunter2" not in repr(found)


def test_markup_in_a_field_is_escaped() -> None:
    page = main(
        open_client(FakeSystem(text=journal(line(**record("<script>alert(1)</script>")))))
        .get("/security")
        .text
    )
    assert "<script>alert(1)" not in page and "&lt;script&gt;" in page


@pytest.mark.parametrize(
    "bad",
    [
        line(event="x", outcome="maybe", service="app"),
        line(event=1, outcome="success", service="app"),
        line(event="x", outcome="success", service=None),
    ],
)
def test_a_record_that_is_malformed_is_dropped(bad: str) -> None:
    assert security_events.parse(journal(bad)) == []


def test_the_newest_come_first_and_a_long_window_is_cut() -> None:
    old = line(**{**record("sign-out"), "time": "2026-11-23T09:00:00.000Z"})
    new = line(**record("sign-in.succeeded"))
    found = security_events.parse(journal(old, new))
    assert [e.event for e in found] == ["sign-in.succeeded", "sign-out"]
    many = journal(*[new] * (security_events.MAX_ENTRIES + 5))
    cut = security_events.read(AdminSettings(systemd=True), FakeSystem(text=many), now=NOW)
    assert cut.truncated and len(cut.entries) == security_events.MAX_ENTRIES

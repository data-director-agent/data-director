"""Sessions kept in a file outlive the process that opened them (docs/specs/policy-and-identity.md,
#900): a store opened afresh over the same file, as after a restart, knows every session the old
one did, with the same limits, and none that was signed out or has ended."""

from __future__ import annotations

import stat
import time
from dataclasses import dataclass, field
from pathlib import Path

from dd_harness.sessions import TOUCH_EVERY_S, SessionStore
from dd_harness.testing import TEST_PRINCIPAL


@dataclass
class Clock:
    now: float = field(default_factory=time.time)

    def __call__(self) -> float:
        return self.now


def reopen(path: Path, clock: Clock) -> SessionStore:
    return SessionStore.open(path, idle_s=600, lifetime_s=3600, clock=clock)


def test_a_session_outlives_a_restart(tmp_path: Path) -> None:
    path, clock = tmp_path / "sessions.db", Clock()
    session_id = reopen(path, clock).create(TEST_PRINCIPAL)
    session = reopen(path, clock).get(session_id)
    assert session is not None
    assert session.principal == TEST_PRINCIPAL


def test_signing_out_holds_across_a_restart(tmp_path: Path) -> None:
    path, clock = tmp_path / "sessions.db", Clock()
    store = reopen(path, clock)
    session_id = store.create(TEST_PRINCIPAL)
    store.delete(session_id)
    assert reopen(path, clock).get(session_id) is None


def test_the_idle_time_and_lifetime_hold_across_a_restart(tmp_path: Path) -> None:
    path, clock = tmp_path / "sessions.db", Clock()
    idle = reopen(path, clock).create(TEST_PRINCIPAL)
    busy = reopen(path, clock).create(TEST_PRINCIPAL)
    began = clock.now
    while clock.now - began < 3600:
        clock.now += 300
        assert (reopen(path, clock).get(busy) is not None) == (clock.now - began < 3600)
        if clock.now - began >= 600:
            assert reopen(path, clock).get(idle) is None


def test_a_request_writes_its_time_only_once_a_minute(tmp_path: Path) -> None:
    path, clock = tmp_path / "sessions.db", Clock()
    session_id = reopen(path, clock).create(TEST_PRINCIPAL)
    began = clock.now
    clock.now += TOUCH_EVERY_S - 1
    reopen(path, clock).get(session_id)
    seen = reopen(path, clock).get(session_id, touch=False)
    assert seen is not None and seen.last_seen == began
    clock.now += 1
    reopen(path, clock).get(session_id)
    seen = reopen(path, clock).get(session_id, touch=False)
    assert seen is not None and seen.last_seen == clock.now


def test_ended_sessions_are_cleared_when_one_is_opened(tmp_path: Path) -> None:
    path, clock = tmp_path / "sessions.db", Clock()
    store = reopen(path, clock)
    store.create(TEST_PRINCIPAL)
    clock.now += 601
    store.create(TEST_PRINCIPAL)
    assert len(reopen(path, clock).table) == 1


def test_only_the_service_reads_the_file(tmp_path: Path) -> None:
    path = tmp_path / "sessions" / "app.db"
    reopen(path, Clock()).create(TEST_PRINCIPAL)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_with_no_file_sessions_are_kept_in_memory() -> None:
    store = SessionStore.open(None)
    session_id = store.create(TEST_PRINCIPAL)
    assert store.get(session_id) is not None
    assert SessionStore.open(None).get(session_id) is None

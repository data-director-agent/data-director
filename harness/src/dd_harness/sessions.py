"""Who is signed in: server-side sessions for a way in that signs people in
(docs/specs/policy-and-identity.md). The app and the workbench each keep their own.

The browser holds an opaque, random session identifier in a cookie and nothing else. The store
keeps, for each session, the `Principal` and the session's times, and nothing more: no token
from the provider. It keeps only a hash of each identifier, so what it holds cannot be replayed
as a cookie.

A session ends after an idle time or a lifetime, whichever comes first, and when its person signs
out. A sign-in that has been started but has not come back from the provider is held here too,
for a short time, under its `state`, with the `nonce` it was sent with.

Sessions are kept in a SQLite file when the way in names one (`SessionStore.open`, set by
`DD_SESSIONS_FILE`), so restarting the server, as each deployment does, signs nobody out; with none
they are kept in memory, and a restart signs everyone out. The file holds the identifiers' hashes,
the principals and the times, readable by the service's user alone. Signing out deletes the row at
once, so a cookie that was signed out stays refused after a restart. A request restarts the idle
time to the nearest `TOUCH_EVERY_S`, so the store is not written on every request: a session may
end up to that much early, never late. A sign-in still at the provider is held in memory only, so a
restart in the middle of one asks the person to sign in again.

A run that is still going when its session ends finishes, and acts for whoever started it, because
`acting_for` is fixed when the conductor is invoked.

The cookie names are the app's by default. A second way in served on the same host, such as the
workbench on another port, names its own, because a browser scopes cookies by host and not by port.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from typing import Protocol

from dd_harness.identity import RefusalReason, Unauthenticated
from dd_sdk.contract.models import Principal
from dd_sdk.sqlite_store import LockedSqlite

SESSION_COOKIE = "dd_session"
# Binds a sign-in's `state` to the browser that started it, so a callback carried to another
# browser (login CSRF) is refused.
SIGN_IN_COOKIE = "dd_sign_in"
# The defaults (docs/specs/policy-and-identity.md): an idle timeout of 8 hours and a lifetime of 7
# days.
DEFAULT_IDLE_S = 8 * 60 * 60
DEFAULT_LIFETIME_S = 7 * 24 * 60 * 60
# How long a person has to sign in at the provider before the sign-in must be started again.
PENDING_S = 10 * 60
# Bytes of randomness in a session identifier, `state` and `nonce`: 256 bits.
TOKEN_BYTES = 32
# Seconds a session's last use is rounded to: a request restarts the idle time, and writes it,
# only once this much has passed since the last write.
TOUCH_EVERY_S = 60


@dataclass
class Session:
    principal: Principal
    created: float
    last_seen: float


@dataclass(frozen=True)
class PendingSignIn:
    nonce: str
    return_to: str
    created: float


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SessionTable(Protocol):
    """Where the sessions are kept, by the hash of their identifiers. It stores and reads, and
    decides nothing: when a session ends is `SessionStore`'s."""

    def put(self, key: str, session: Session) -> None: ...
    def get(self, key: str) -> Session | None: ...
    def touch(self, key: str, when: float) -> None: ...
    def delete(self, key: str) -> None: ...
    def prune(self, idle_before: float, created_before: float) -> None:
        """Forget every session last seen before `idle_before` or created before
        `created_before`."""

    def __len__(self) -> int: ...


class MemorySessions:
    """Sessions in this process's memory: a restart forgets them."""

    def __init__(self) -> None:
        self._rows: dict[str, Session] = {}

    def put(self, key: str, session: Session) -> None:
        self._rows[key] = Session(session.principal, session.created, session.last_seen)

    def get(self, key: str) -> Session | None:
        row = self._rows.get(key)
        return None if row is None else Session(row.principal, row.created, row.last_seen)

    def touch(self, key: str, when: float) -> None:
        if key in self._rows:
            self._rows[key].last_seen = when

    def delete(self, key: str) -> None:
        self._rows.pop(key, None)

    def prune(self, idle_before: float, created_before: float) -> None:
        self._rows = {
            k: s
            for k, s in self._rows.items()
            if s.last_seen >= idle_before and s.created >= created_before
        }

    def __len__(self) -> int:
        return len(self._rows)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    digest TEXT PRIMARY KEY,
    principal TEXT NOT NULL,
    created REAL NOT NULL,
    last_seen REAL NOT NULL
);
"""


class SqliteSessions:
    """Sessions in a SQLite file, which outlive the process. The file is made readable by its
    owner alone before anything is written to it."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
        path.chmod(0o600)
        self._connect = LockedSqlite(path, _SCHEMA).connect

    def put(self, key: str, session: Session) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO sessions (digest, principal, created, last_seen)"
                " VALUES (?, ?, ?, ?)",
                (key, session.principal.model_dump_json(), session.created, session.last_seen),
            )

    def get(self, key: str) -> Session | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT principal, created, last_seen FROM sessions WHERE digest = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        return Session(Principal.model_validate_json(row[0]), row[1], row[2])

    def touch(self, key: str, when: float) -> None:
        with self._connect() as db:
            db.execute("UPDATE sessions SET last_seen = ? WHERE digest = ?", (when, key))

    def delete(self, key: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM sessions WHERE digest = ?", (key,))

    def prune(self, idle_before: float, created_before: float) -> None:
        with self._connect() as db:
            db.execute(
                "DELETE FROM sessions WHERE last_seen < ? OR created < ?",
                (idle_before, created_before),
            )

    def __len__(self) -> int:
        with self._connect() as db:
            (count,) = db.execute("SELECT count(*) FROM sessions").fetchone()
        return int(count)


@dataclass
class SessionStore:
    idle_s: int = DEFAULT_IDLE_S
    lifetime_s: int = DEFAULT_LIFETIME_S
    clock: Callable[[], float] = time.time
    table: SessionTable = field(default_factory=MemorySessions, repr=False)
    _pending: dict[str, PendingSignIn] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def open(
        cls,
        path: Path | None,
        idle_s: int = DEFAULT_IDLE_S,
        lifetime_s: int = DEFAULT_LIFETIME_S,
        *,
        clock: Callable[[], float] = time.time,
    ) -> SessionStore:
        """A store whose sessions are kept in the SQLite file at `path`, and outlive the
        process; in memory if `path` is None."""
        table: SessionTable = MemorySessions() if path is None else SqliteSessions(path)
        return cls(idle_s, lifetime_s, clock, table)

    def begin(self, return_to: str) -> tuple[str, str]:
        """A new sign-in's `state` and `nonce`, held until the provider sends the person back."""
        state, nonce = secrets.token_urlsafe(TOKEN_BYTES), secrets.token_urlsafe(TOKEN_BYTES)
        with self._lock:
            now = self.clock()
            self._pending = {k: p for k, p in self._pending.items() if now - p.created < PENDING_S}
            self._pending[state] = PendingSignIn(nonce, return_to, now)
        return state, nonce

    def take(self, state: str) -> PendingSignIn | None:
        """The sign-in started with `state`, once: a second callback with it finds nothing."""
        with self._lock:
            pending = self._pending.pop(state, None)
        if pending is None or self.clock() - pending.created >= PENDING_S:
            return None
        return pending

    def create(self, principal: Principal) -> str:
        """A new session for `principal`, and the identifier the browser is to hold."""
        session_id = secrets.token_urlsafe(TOKEN_BYTES)
        with self._lock:
            now = self.clock()
            # Ended sessions are forgotten here, so they do not pile up with no timer to clear them.
            self.table.prune(now - self.idle_s, now - self.lifetime_s)
            self.table.put(_digest(session_id), Session(principal, now, now))
        return session_id

    def get(self, session_id: str, *, touch: bool = True) -> Session | None:
        """The live session `session_id` names, its idle time restarted unless `touch` is false
        (to the nearest `TOUCH_EVERY_S`); an ended one is forgotten."""
        key = _digest(session_id)
        with self._lock:
            session = self.table.get(key)
            if session is None:
                return None
            now = self.clock()
            if now >= self.expires_at(session):
                self.table.delete(key)
                return None
            if touch and now - session.last_seen >= TOUCH_EVERY_S:
                session.last_seen = now
                self.table.touch(key, now)
            return session

    def delete(self, session_id: str) -> None:
        with self._lock:
            self.table.delete(_digest(session_id))

    def expires_at(self, session: Session) -> float:
        """When `session` ends if nothing more is done in it."""
        return min(session.last_seen + self.idle_s, session.created + self.lifetime_s)


def cookie(headers: Mapping[str, str] | None, name: str) -> str | None:
    """The value of cookie `name` in a request's headers, if it has one."""
    if headers is None:
        return None
    jar: SimpleCookie = SimpleCookie()
    for key, value in headers.items():
        if key.lower() == "cookie":
            try:
                jar.load(value)
            except CookieError:
                return None
    morsel = jar.get(name)
    return morsel.value if morsel is not None and morsel.value else None


@dataclass(frozen=True)
class SessionAuthenticator:
    """The person a request's session cookie names (docs/specs/policy-and-identity.md). A request
    with no session, or one that has ended, is refused; it is never given the operator's
    principal."""

    store: SessionStore
    cookie_name: str = SESSION_COOKIE

    def session(self, headers: Mapping[str, str] | None, *, touch: bool = True) -> Session | None:
        """The live session the request's cookie names. Reading it restarts its idle time, unless
        `touch` is false: asking when a session ends does not keep it going."""
        session_id = cookie(headers, self.cookie_name)
        return self.store.get(session_id, touch=touch) if session_id else None

    def principal_for(self, headers: Mapping[str, str] | None) -> Principal:
        session = self.session(headers)
        if session is None:
            raise Unauthenticated(
                "not signed in, or the session has ended: sign in to act", RefusalReason.NO_SESSION
            )
        return session.principal

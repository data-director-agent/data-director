"""Who is signed in: the app's server-side sessions (ADR-0029).

The browser holds an opaque, random session identifier in a cookie and nothing else. The store
keeps, for each session, the `Principal` and the session's times, and nothing more: no token
from the provider. It keeps only a hash of each identifier, so what it holds cannot be replayed
as a cookie.

A session ends after an idle time or a lifetime, whichever comes first, and when its person signs
out. A sign-in that has been started but has not come back from the provider is held here too,
for a short time, under its `state`, with the `nonce` it was sent with.

The store is in memory, for the alpha's single server process: restarting the app signs everyone
out. A run that is still going when its session ends finishes, and acts for whoever started it,
because `acting_for` is fixed when the conductor is invoked.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http.cookies import CookieError, SimpleCookie

from dd_harness.identity import Unauthenticated
from dd_sdk.contract.models import Principal

SESSION_COOKIE = "dd_session"
# Binds a sign-in's `state` to the browser that started it, so a callback carried to another
# browser (login CSRF) is refused.
SIGN_IN_COOKIE = "dd_sign_in"
# ADR-0029's proposed defaults: an idle timeout of 8 hours and a lifetime of 7 days.
DEFAULT_IDLE_S = 8 * 60 * 60
DEFAULT_LIFETIME_S = 7 * 24 * 60 * 60
# How long a person has to sign in at the provider before the sign-in must be started again.
PENDING_S = 10 * 60
# Bytes of randomness in a session identifier, `state` and `nonce`: 256 bits.
TOKEN_BYTES = 32


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


@dataclass
class SessionStore:
    idle_s: int = DEFAULT_IDLE_S
    lifetime_s: int = DEFAULT_LIFETIME_S
    clock: Callable[[], float] = time.time
    _sessions: dict[str, Session] = field(default_factory=dict, repr=False)
    _pending: dict[str, PendingSignIn] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

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
            self._sessions[_digest(session_id)] = Session(principal, now, now)
        return session_id

    def get(self, session_id: str, *, touch: bool = True) -> Session | None:
        """The live session `session_id` names, its idle time restarted unless `touch` is false;
        an ended one is forgotten."""
        key = _digest(session_id)
        with self._lock:
            session = self._sessions.get(key)
            if session is None:
                return None
            now = self.clock()
            if now >= self.expires_at(session):
                del self._sessions[key]
                return None
            if touch:
                session.last_seen = now
            return session

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(_digest(session_id), None)

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
    """The person a request's session cookie names (ADR-0029). A request with no session, or one
    that has ended, is refused; it is never given the operator's principal."""

    store: SessionStore

    def session(self, headers: Mapping[str, str] | None, *, touch: bool = True) -> Session | None:
        """The live session the request's cookie names. Reading it restarts its idle time, unless
        `touch` is false: asking when a session ends does not keep it going."""
        session_id = cookie(headers, SESSION_COOKIE)
        return self.store.get(session_id, touch=touch) if session_id else None

    def principal_for(self, headers: Mapping[str, str] | None) -> Principal:
        session = self.session(headers)
        if session is None:
            raise Unauthenticated("not signed in, or the session has ended: sign in to act")
        return session.principal

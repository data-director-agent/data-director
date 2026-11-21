"""The deposit broker's records, by pseudonym.

One SQLite file holds three tables:

- `accounts`: one row per person and repository API root. The tokens are sealed
  (`dd_deposit_broker.seal`): an access token, and, for an account connected through OAuth, its
  refresh token and when the access token expires. The label is what the Settings page shows.
- `oauth_states`: the `state` of each OAuth authorisation under way, with the pseudonym it is
  for, the PKCE verifier and a nonce the browser holds in a cookie, each until it expires.
- `used`: the identifiers of tickets and grants already accepted, each until shortly after it
  expires, so that each is accepted once.

No item, package or repository answer is ever written here. Disconnecting an account deletes its
row at once.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from dd_deposit_broker.seal import Sealed, seal, unseal
from dd_sdk.sqlite_store import LockedSqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    pseudonym TEXT NOT NULL,
    base_url TEXT NOT NULL,
    method TEXT NOT NULL,
    label TEXT NOT NULL,
    nonce BLOB NOT NULL,
    ciphertext BLOB NOT NULL,
    created TEXT NOT NULL,
    PRIMARY KEY (pseudonym, base_url)
);
CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    pseudonym TEXT NOT NULL,
    base_url TEXT NOT NULL,
    verifier TEXT NOT NULL,
    browser TEXT NOT NULL,
    expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS used (
    jti TEXT PRIMARY KEY,
    expires INTEGER NOT NULL
);
"""

# How a person connected an account.
OAUTH = "oauth"
TOKEN = "token"


@dataclass(frozen=True)
class Tokens:
    """A person's tokens for one repository, unsealed for one deposit. Kept out of `repr`."""

    access_token: str = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    # When the access token expires, in seconds since the epoch; None if it does not say.
    expires_at: int | None = None

    def to_bytes(self) -> bytes:
        return json.dumps(
            {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.expires_at,
            }
        ).encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> Tokens:
        loaded = json.loads(data)
        return cls(loaded["access_token"], loaded.get("refresh_token"), loaded.get("expires_at"))


@dataclass(frozen=True)
class Account:
    """A person's account at one repository: what the Settings page may show, and the tokens."""

    base_url: str
    method: str
    label: str
    created: datetime
    tokens: Tokens = field(repr=False)


@dataclass(frozen=True)
class PendingAuthorisation:
    pseudonym: str = field(repr=False)
    base_url: str
    verifier: str = field(repr=False)
    browser: str = field(repr=False)


class Store:
    def __init__(
        self, path: Path, key_encryption_key: bytes, *, now: Callable[[], float] = time.time
    ) -> None:
        self.path = path
        self._kek = key_encryption_key
        self._now = now
        self._connect = LockedSqlite(path, _SCHEMA).connect

    def put(
        self, pseudonym: str, base_url: str, tokens: Tokens, *, method: str, label: str
    ) -> None:
        """Add or replace a person's account at `base_url`, sealing the tokens."""
        sealed = seal(self._kek, pseudonym, base_url, tokens.to_bytes())
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO accounts"
                " (pseudonym, base_url, method, label, nonce, ciphertext, created)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    pseudonym,
                    base_url,
                    method,
                    label,
                    sealed.nonce,
                    sealed.ciphertext,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def account(self, pseudonym: str, base_url: str) -> Account | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT method, label, nonce, ciphertext, created FROM accounts"
                " WHERE pseudonym = ? AND base_url = ?",
                (pseudonym, base_url),
            ).fetchone()
        if row is None:
            return None
        method, label, nonce, ciphertext, created = row
        tokens = Tokens.from_bytes(
            unseal(self._kek, pseudonym, base_url, Sealed(nonce, ciphertext))
        )
        return Account(base_url, method, label, datetime.fromisoformat(created), tokens)

    def replace_tokens(self, pseudonym: str, base_url: str, tokens: Tokens) -> None:
        """Keep refreshed tokens for an account that is still connected; if the person has
        disconnected it meanwhile, nothing is written."""
        sealed = seal(self._kek, pseudonym, base_url, tokens.to_bytes())
        with self._connect() as db:
            db.execute(
                "UPDATE accounts SET nonce = ?, ciphertext = ?"
                " WHERE pseudonym = ? AND base_url = ?",
                (sealed.nonce, sealed.ciphertext, pseudonym, base_url),
            )

    def remove(self, pseudonym: str, base_url: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "DELETE FROM accounts WHERE pseudonym = ? AND base_url = ?", (pseudonym, base_url)
            )
        return cursor.rowcount > 0

    def begin_authorisation(
        self, state: str, pending: PendingAuthorisation, *, lifetime_s: int
    ) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM oauth_states WHERE expires < ?", (int(self._now()),))
            db.execute(
                "INSERT INTO oauth_states (state, pseudonym, base_url, verifier, browser, expires)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    state,
                    pending.pseudonym,
                    pending.base_url,
                    pending.verifier,
                    pending.browser,
                    int(self._now()) + lifetime_s,
                ),
            )

    def finish_authorisation(self, state: str) -> PendingAuthorisation | None:
        """The authorisation `state` names, removed so that it is finished once; None if there is
        none or it has expired."""
        with self._connect() as db:
            row = db.execute(
                "SELECT pseudonym, base_url, verifier, browser, expires FROM oauth_states"
                " WHERE state = ?",
                (state,),
            ).fetchone()
            db.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        if row is None or row[4] < int(self._now()):
            return None
        return PendingAuthorisation(row[0], row[1], row[2], row[3])

    def use_once(self, jti: str, expires: int) -> bool:
        """Record a ticket's or grant's identifier; False if it was already used."""
        with self._connect() as db:
            db.execute("DELETE FROM used WHERE expires < ?", (int(self._now()),))
            try:
                db.execute("INSERT INTO used (jti, expires) VALUES (?, ?)", (jti, expires))
            except sqlite3.IntegrityError:
                return False
        return True

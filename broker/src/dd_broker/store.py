"""The broker's records: sealed keys and token counts, by pseudonym (docs/specs/model-accounts.md).

One SQLite file holds two tables:

- `accounts`: one row per person who has enrolled a key. The key itself is sealed
  (`dd_broker.seal`); the label is what the Profile page shows (the provider, the account's name
  if the provider gives one, and the last four characters of the key).
- `usage`: input and output tokens per pseudonym, day, payer, provider and model.

No prompt and no reply is ever written here. Removing an account deletes its row at once.
Enrolment over HTTP is TODO(#807); it will call `put` and `remove`.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from dd_broker.seal import Sealed, seal, unseal
from dd_sdk.model_grant import Payer

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    pseudonym TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    base_url TEXT,
    label TEXT NOT NULL,
    nonce BLOB NOT NULL,
    ciphertext BLOB NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    pseudonym TEXT NOT NULL,
    day TEXT NOT NULL,
    payer TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (pseudonym, day, payer, provider, model)
);
"""


@dataclass(frozen=True)
class OwnAccount:
    """A person's own account, unsealed for one call. The key is kept out of `repr`."""

    provider: str
    base_url: str | None
    label: str
    key: str = field(repr=False)


@dataclass(frozen=True)
class Usage:
    day: date
    payer: Payer
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


class Store:
    def __init__(self, path: Path, key_encryption_key: bytes) -> None:
        self.path = path
        self._kek = key_encryption_key
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            db = sqlite3.connect(self.path)
            try:
                with db:
                    yield db
            finally:
                db.close()

    def put(
        self,
        pseudonym: str,
        provider: str,
        key: str,
        *,
        label: str,
        base_url: str | None = None,
    ) -> None:
        """Add or replace a person's account, sealing the key."""
        sealed = seal(self._kek, pseudonym, key)
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO accounts"
                " (pseudonym, provider, base_url, label, nonce, ciphertext, created)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    pseudonym,
                    provider,
                    base_url,
                    label,
                    sealed.nonce,
                    sealed.ciphertext,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def account(self, pseudonym: str) -> OwnAccount | None:
        """The person's account with its key unsealed, or `None` if they have none. Raises
        `SealError` if the sealed key does not open."""
        with self._connect() as db:
            row = db.execute(
                "SELECT provider, base_url, label, nonce, ciphertext FROM accounts"
                " WHERE pseudonym = ?",
                (pseudonym,),
            ).fetchone()
        if row is None:
            return None
        provider, base_url, label, nonce, ciphertext = row
        key = unseal(self._kek, pseudonym, Sealed(nonce=nonce, ciphertext=ciphertext))
        return OwnAccount(provider=provider, base_url=base_url, label=label, key=key)

    def remove(self, pseudonym: str) -> bool:
        """Erase a person's account at once. Whether there was one."""
        with self._connect() as db:
            cursor = db.execute("DELETE FROM accounts WHERE pseudonym = ?", (pseudonym,))
        return cursor.rowcount > 0

    def add_usage(
        self,
        pseudonym: str,
        *,
        payer: Payer,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        day: date | None = None,
    ) -> None:
        day = day or datetime.now(UTC).date()
        with self._connect() as db:
            db.execute(
                "INSERT INTO usage"
                " (pseudonym, day, payer, provider, model, input_tokens, output_tokens)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (pseudonym, day, payer, provider, model) DO UPDATE SET"
                " input_tokens = input_tokens + excluded.input_tokens,"
                " output_tokens = output_tokens + excluded.output_tokens",
                (
                    pseudonym,
                    day.isoformat(),
                    payer.value,
                    provider,
                    model,
                    input_tokens,
                    output_tokens,
                ),
            )

    def usage(self, pseudonym: str) -> list[Usage]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT day, payer, provider, model, input_tokens, output_tokens FROM usage"
                " WHERE pseudonym = ? ORDER BY day, payer, provider, model",
                (pseudonym,),
            ).fetchall()
        return [
            Usage(
                day=date.fromisoformat(day),
                payer=Payer(payer),
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            for day, payer, provider, model, input_tokens, output_tokens in rows
        ]

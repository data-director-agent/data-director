"""Where cached answers are kept: one SQLite table, in a file or in memory.

Each entry is an answer to one key: the body as the registry sent it, or a note that the registry
had no such record, with the validator it gave (an `ETag`), when the answer was fetched and when
it was last confirmed current. Errors are never stored.

A file is opened in write-ahead-log mode, with one connection per call under a lock, so several
threads of one process share it safely. Without a path the table is kept in memory for the life
of the `Store`.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    key TEXT PRIMARY KEY,
    missing INTEGER NOT NULL,
    body BLOB NOT NULL,
    content_type TEXT NOT NULL,
    etag TEXT,
    fetched_at REAL NOT NULL,
    checked_at REAL NOT NULL
)
"""
COLUMNS = "key, missing, body, content_type, etag, fetched_at, checked_at"


@dataclass(frozen=True)
class Entry:
    """One stored answer. `fetched_at` is when its body was last received; `checked_at` is when
    the registry last confirmed it, by sending it or by answering 304. Both are POSIX seconds."""

    key: str
    missing: bool
    body: bytes
    content_type: str
    etag: str | None
    fetched_at: float
    checked_at: float


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._memory: sqlite3.Connection | None = None
        if path is None:
            self._memory = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            if path is not None:
                db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            memory = self._memory
            db = memory if memory is not None else sqlite3.connect(self.path or ":memory:")
            try:
                with db:
                    yield db
            finally:
                if memory is None:
                    db.close()

    def close(self) -> None:
        """Close the in-memory table, losing it; a file needs no closing."""
        if self._memory is not None:
            self._memory.close()
            self._memory = None

    def __del__(self) -> None:
        memory = getattr(self, "_memory", None)
        if memory is not None:
            memory.close()

    def get(self, key: str) -> Entry | None:
        with self._connect() as db:
            row = db.execute(f"SELECT {COLUMNS} FROM entries WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return Entry(row[0], bool(row[1]), bytes(row[2]), row[3], row[4], row[5], row[6])

    def put(self, entry: Entry) -> None:
        with self._connect() as db:
            db.execute(
                f"INSERT OR REPLACE INTO entries ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.key,
                    int(entry.missing),
                    entry.body,
                    entry.content_type,
                    entry.etag,
                    entry.fetched_at,
                    entry.checked_at,
                ),
            )

    def touch(self, key: str, checked_at: float) -> None:
        """Record that the registry confirmed the entry current at `checked_at`."""
        with self._connect() as db:
            db.execute("UPDATE entries SET checked_at = ? WHERE key = ?", (checked_at, key))

    def clear(self, prefix: str = "") -> int:
        """Remove every entry whose key starts with `prefix` (all of them by default); the
        number removed."""
        with self._connect() as db:
            cur = db.execute(
                "DELETE FROM entries WHERE substr(key, 1, ?) = ?", (len(prefix), prefix)
            )
        return cur.rowcount

    def count(self) -> int:
        with self._connect() as db:
            (n,) = db.execute("SELECT count(*) FROM entries").fetchone()
        return int(n)

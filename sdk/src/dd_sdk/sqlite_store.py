"""One SQLite file a service keeps for itself, such as a broker's sealed keys or tokens.

Each call opens its own connection under one lock, in a transaction that commits when the block
ends and rolls back if it raises, and closes it; the file is in write-ahead-log mode, so a backup
can copy it while the service runs. The services that hold people's own credentials
(`dd_broker.store`, `dd_deposit_broker.store`) build their stores on it.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class LockedSqlite:
    def __init__(self, path: Path, schema: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(schema)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            db = sqlite3.connect(self.path)
            try:
                with db:
                    yield db
            finally:
                db.close()

"""The PostgreSQL backend of `ConversationLocks` (`dd_harness.turn_locks`, docs/specs/storage.md,
"Turn locks").

Each held lock is a session-level advisory lock, `pg_try_advisory_lock(TURN_LOCKS, hashtext(id))`,
on a connection of its own, opened for the turn and closed when it is released. A turn may run
for minutes, so the lock does not borrow from a store's pool, where it would keep a connection
from the runs being stored. A connection the server loses releases its lock with it (guarantee 4).

Advisory locks belong to the database, not to a schema: two deployments on one database, each in
a schema of its own, share them. `hashtext` is 32 bits, so two conversations may share a lock; a
turn refused for that reason is refused as if its own conversation were busy, and may be sent
again.
"""

from __future__ import annotations

import psycopg

from dd_harness.postgres import _open
from dd_harness.turn_locks import Release, _once

# The first key of every turn lock, apart from the store's own one-key locks.
TURN_LOCKS = 0x6464_7475  # "ddtu"


class PostgresConversationLocks:
    """Turn locks on the database at `location`, whose schema must be this build's: one that is
    not stops start-up with `SettingsError`, as the stores do."""

    def __init__(self, location: str) -> None:
        self._where = _open(location)
        self._location = location

    def try_hold(self, conversation_id: str) -> Release | None:
        conn = psycopg.connect(self._location, autocommit=True)
        try:
            row = conn.execute(
                "select pg_try_advisory_lock(%s, hashtext(%s))", (TURN_LOCKS, conversation_id)
            ).fetchone()
        except BaseException:
            conn.close()
            raise
        if row is None or not row[0]:
            conn.close()
            return None
        return _once(conn.close)  # the session's end releases its advisory locks

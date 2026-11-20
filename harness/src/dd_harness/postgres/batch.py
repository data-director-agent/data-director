"""Reading several runs in one query (`RunStorage.get_many`, docs/specs/storage.md, "Listing")."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from psycopg import sql

from dd_harness.postgres.pool import Pooled, recovering
from dd_harness.store import RUN_ID

PARTS = ("envelope", "request")


class BatchReads(Pooled):
    """`get_many` for a store that holds a connection pool."""

    @recovering
    def get_many(self, ids: Collection[str], part: str = "envelope") -> dict[str, Any]:
        if part not in PARTS:
            raise ValueError(f"not a part of a run: {part!r}")
        named = sorted({i for i in ids if RUN_ID.fullmatch(i)})
        if not named:
            return {}
        query = sql.SQL(
            "select invocation_id, {} from runs where invocation_id = any(%s::text[])"
        ).format(sql.Identifier(part))
        with self._pool.connection() as conn:
            rows = conn.execute(query, (named,)).fetchall()
        return {invocation_id: document for invocation_id, document in rows if document is not None}

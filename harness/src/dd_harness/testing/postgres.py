"""PostgreSQL helpers that the backend's tests and its benchmark share (docs/specs/storage.md).

Each caller keeps its stores in schemas of its own on one database, so callers running side by
side do not meet. `bulk_runs` fills a run store with synthetic runs in one statement, as a store
that has been in use for a while, without running the conductor that many times. Needs the
harness's `postgres` extra.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import LiteralString
from urllib.parse import quote

import psycopg

from dd_harness import postgres

# Runs in many conversations, some delegated, for many principals, a third of them in projects.
LARGE_STORE: LiteralString = """
insert into runs (invocation_id, conversation_id, envelope)
select
    'run-' || i,
    'conversation-' || (i %% 5000),
    json_build_object(
        'invocation_id', 'run-' || i,
        'agent_id', 'stub.storage',
        'agent_version', '0.1.0',
        'conversation_id', 'conversation-' || (i %% 5000),
        'parent_invocation_id', case when i %% 10 = 0 then 'run-' || (i - 1) end,
        'project_id', case when (i %% 5000) %% 3 = 0 then 'project-' || (i %% 40) end,
        'acting_for', json_build_object(
            'principal_id', 'principal-' || ((i %% 5000) %% 50), 'name', 'Person ' || (i %% 50)
        ),
        'completed_at', to_char(timestamp '2026-01-01' + i * interval '1 second',
            'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
        'outcome', json_build_object('status', 'succeeded', 'statement', 'Stored.')
    )
from generate_series(1, %(runs)s) as i
"""


def in_schema(database: str, schema: str) -> str:
    """`database`, with `schema` first on its search path."""
    option = quote(f"-csearch_path={schema}", safe="")
    return f"{database}{'&' if '?' in database else '?'}options={option}"


def at_version_one(location: str) -> None:
    """Apply the first migration alone, as a database made before listing was indexed."""
    _version, name, script = postgres.migrations()[0]
    with psycopg.connect(location) as conn, conn.transaction():
        conn.execute(
            "create table dd_schema (version integer primary key, name text not null,"
            " applied_at timestamptz not null default now())"
        )
        conn.execute(script.encode())
        conn.execute("insert into dd_schema (version, name) values (1, %s)", (name,))


def bulk_runs(location: str, runs: int) -> None:
    """Fill the empty schema at `location` with `runs` synthetic runs (`LARGE_STORE`), migrate
    it to the current version, which indexes them as it would runs stored since, and analyse it
    so that the planner knows its size."""
    at_version_one(location)
    with psycopg.connect(location) as conn:
        conn.execute(LARGE_STORE, {"runs": runs})
    postgres.migrate(location)
    with psycopg.connect(location, autocommit=True) as conn:
        conn.execute("analyze")


@contextmanager
def scratch_schemas(database: str) -> Iterator[ScratchSchemas]:
    """Schemas made on `database` by name, each dropped on leaving."""
    schemas = ScratchSchemas(database)
    try:
        yield schemas
    finally:
        schemas.drop()


class ScratchSchemas:
    """Empty schemas on one database, by name: the same name opens the same one."""

    def __init__(self, database: str) -> None:
        self.database = database
        self.prefix = f"dd_test_{uuid.uuid4().hex[:12]}"
        self.made: dict[str, str] = {}

    def blank(self, name: str) -> str:
        """The location of the empty schema called `name`, made on first use."""
        if name not in self.made:
            schema = f"{self.prefix}_{re.sub(r'[^a-z0-9]', '_', name.lower())}"
            with psycopg.connect(self.database, autocommit=True) as conn:
                conn.execute(f'create schema "{schema}"'.encode())
            self.made[name] = in_schema(self.database, schema)
        return self.made[name]

    def migrated(self, name: str) -> str:
        """The location of the schema called `name`, migrated to the current version."""
        fresh = name not in self.made
        location = self.blank(name)
        if fresh:
            postgres.migrate(location)
        return location

    def drop(self) -> None:
        with psycopg.connect(self.database, autocommit=True) as conn:
            for location in self.made.values():
                schema = location.rsplit("%3D", 1)[1]
                conn.execute(f'drop schema "{schema}" cascade'.encode())
        self.made.clear()

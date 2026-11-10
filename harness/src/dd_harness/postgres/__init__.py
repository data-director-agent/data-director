"""The PostgreSQL backend of `RunStorage` and `ProjectLog` (`dd_harness.storage`,
docs/specs/storage.md).

A location is a `postgresql://` URL that names the database and never a credential: libpq takes
those from its password file, service file or environment (invariant 13). The tables are in the
first schema of the connection's `search_path`; a location may choose one with
`?options=-csearch_path%3D<schema>`.

The schema changes only through the numbered SQL files in `migrations/`, applied by `migrate`
(`dd-harness storage migrate`). A store refuses to open over a schema that is older or newer than
this build's, naming that command, and nothing alters a schema as a side effect of serving.

Each store keeps a pool of connections (`psycopg_pool`), at most `pool_size` of them
(`DD_POSTGRES_POOL_SIZE` through `dd_harness.settings`), and each call borrows one for its length,
so a store is safe to share between threads. `close` releases the pool, as does the store being
collected or the process ending. A store is opened in the process that uses it, never carried
across a `fork`. A project's exclusive section is a transaction that holds a lock on the
project's row (`select … for update`), which holds across processes and hosts; projects do not
wait on one another. It stores and reads, and decides nothing: the project rules are
`dd_harness.projects.Projects`, over this log.

Listing runs and conversations reads one page from an index, whatever the size of the store
(docs/specs/storage.md, "Listing"). `conversation_index` holds a row per conversation, written in
the transaction that stores each turn. `runs_query` and `conversations_query` build the SQL a
listing runs, so a test can ask the database how it plans it. Each project event's
`names_principal` is the principal whose role it may change, indexed, so that the projects a
person may read are found without reading every log (`projects_naming`, `projects_naming_query`).
"""

from __future__ import annotations

import re
import weakref
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from importlib.resources import files
from typing import Any, Self

import psycopg
from psycopg import errors, sql
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from dd_harness.listing import (
    Page,
    Readable,
    check_limit,
    is_turn,
    paged,
    position,
    principal_of,
)
from dd_harness.role_events import names
from dd_harness.settings import SettingsError, redact_location
from dd_harness.store import DIGEST, RUN_ID, artifact_segments
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import UUID7_PATTERN

MIGRATE_COMMAND = "dd-harness storage migrate"
_MIGRATION = re.compile(r"(\d{4})_[a-z0-9_]+\.sql")
_PROJECT_ID = re.compile(UUID7_PATTERN)
_CONVERSATION_STARTED = "conversation_started"
# Taken while a run is stored, so runs are committed in the order of their `seq`, and a reader
# never sees a later run before an earlier one (invariant 3). Held for one insert.
_RUN_ORDER_LOCK = 0x6464_7275_6E73  # "ddruns"
# Taken while the schema is migrated, so two commands never apply the same file.
_MIGRATE_LOCK = 0x6464_6D69_6772  # "ddmigr"
# The most connections one store keeps, unless `DD_POSTGRES_POOL_SIZE` says otherwise.
DEFAULT_POOL_SIZE = 10


def migrations() -> list[tuple[int, str, str]]:
    """This build's numbered SQL files, in order: (version, name, SQL)."""
    found = []
    for entry in files(__package__).joinpath("migrations").iterdir():
        match = _MIGRATION.fullmatch(entry.name)
        if match:
            found.append((int(match.group(1)), entry.name, entry.read_text(encoding="utf-8")))
    found.sort()
    versions = [version for version, _, _ in found]
    if versions != list(range(1, len(found) + 1)):
        raise RuntimeError(f"the migrations are not numbered 1, 2, …: {versions}")
    return found


SCHEMA_VERSION = len(migrations())


def _connect(location: str) -> psycopg.Connection[Any]:
    return psycopg.connect(location)


def schema_version(location: str) -> int:
    """The version of the schema at `location`: 0 if none has been applied."""
    with _connect(location) as conn:
        return _version(conn)


def _version(conn: psycopg.Connection[Any]) -> int:
    row = conn.execute("select to_regclass('dd_schema') is not null").fetchone()
    if row is None or not row[0]:
        return 0
    found = conn.execute("select coalesce(max(version), 0) from dd_schema").fetchone()
    return int(found[0]) if found else 0


def migrate(location: str) -> list[str]:
    """Apply each of this build's SQL files the schema at `location` lacks, in order, and record
    it. Returns the names of the files applied; none if the schema is current. Refuses a schema
    newer than this build's."""
    applied = []
    with _connect(location) as conn, conn.transaction():
        conn.execute("select pg_advisory_xact_lock(%s)", (_MIGRATE_LOCK,))
        conn.execute(
            "create table if not exists dd_schema ("
            " version integer primary key,"
            " name text not null,"
            " applied_at timestamptz not null default now())"
        )
        current = _version(conn)
        if current > SCHEMA_VERSION:
            raise SettingsError(
                f"{redact_location(location)}: the storage schema is at version {current}, "
                f"newer than this build's {SCHEMA_VERSION}; upgrade the harness"
            )
        for version, name, script in migrations():
            if version <= current:
                continue
            conn.execute(script.encode())
            conn.execute("insert into dd_schema (version, name) values (%s, %s)", (version, name))
            applied.append(name)
    return applied


def _open(location: str) -> str:
    """Check that the schema at `location` is this build's, and return the location as a person
    may read it. Raises `SettingsError` if the database cannot be reached or its schema is not
    this build's, so a deployment stops at start-up rather than at its first request."""
    where = redact_location(location)
    try:
        version = schema_version(location)
    except psycopg.Error as exc:
        detail = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        raise SettingsError(f"{where} cannot be used: {detail}") from exc
    if version != SCHEMA_VERSION:
        raise SettingsError(
            f"{where} cannot be used: its storage schema is at version {version} and this build "
            f"expects {SCHEMA_VERSION}; run `{MIGRATE_COMMAND}` (docs/specs/storage.md)"
        )
    return where


type Pool = ConnectionPool[psycopg.Connection[Any]]


def _pool(owner: object, location: str, where: str, size: int) -> Pool:
    """A pool of at most `size` connections to `location`, closed when `owner` is collected or the
    process ends. Each connection is checked as it is borrowed, so one the server dropped (a
    restart) is replaced rather than handed out. The pool is named by `where`, which holds no
    credential, so its log records hold none either."""
    if size < 1:
        raise ValueError(f"a pool holds at least one connection, not {size}")
    pool: Pool = ConnectionPool(
        location,
        min_size=1,
        max_size=size,
        open=True,
        check=ConnectionPool.check_connection,
        name=where,
    )
    weakref.finalize(owner, pool.close)
    return pool


class _Pooled:
    """What both stores share: a pool, released by `close` or at the end of a `with` block."""

    _pool: Pool

    @property
    def pool_size(self) -> int:
        """The most connections the store keeps open at once."""
        return self._pool.max_size

    def close(self) -> None:
        """Close the store's connections. A call after this raises."""
        self._pool.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class PostgresRunStore(_Pooled):
    """Runs kept in PostgreSQL. A run, its request, its prompts and its class schemas are stored
    in one transaction (invariant 4)."""

    def __init__(self, location: str, *, pool_size: int = DEFAULT_POOL_SIZE) -> None:
        self._where = _open(location)
        self._pool = _pool(self, location, self._where, pool_size)

    def has(self, invocation_id: str) -> bool:
        if not RUN_ID.fullmatch(invocation_id):
            return False
        with self._pool.connection() as conn:
            row = conn.execute(
                "select 1 from runs where invocation_id = %s", (invocation_id,)
            ).fetchone()
        return row is not None

    def append(
        self,
        envelope: dict[str, Any],
        request: dict[str, Any] | None = None,
        schemas: Iterable[ClassSchema] = (),
        prompts: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        """Store one run whole, or nothing of it. Raises `FileExistsError` if its
        `invocation_id` is already stored."""
        invocation_id = envelope["invocation_id"]
        if not RUN_ID.fullmatch(invocation_id):
            raise ValueError(f"{invocation_id!r} is not an invocation identifier")
        try:
            with self._pool.connection() as conn, conn.transaction():
                for schema in schemas:
                    conn.execute(
                        "insert into run_schemas (digest, schema) values (%s, %s)"
                        " on conflict (digest) do nothing",
                        (schema.digest, Json(dict(schema.json_schema))),
                    )
                conn.execute("select pg_advisory_xact_lock(%s)", (_RUN_ORDER_LOCK,))
                row = conn.execute(
                    "insert into runs (invocation_id, conversation_id, parent_invocation_id,"
                    " project_id, principal_id, envelope, request, prompts)"
                    " values (%s, %s, %s, %s, %s, %s, %s, %s) returning seq",
                    (
                        invocation_id,
                        envelope.get("conversation_id"),
                        envelope.get("parent_invocation_id"),
                        envelope.get("project_id"),
                        principal_of(envelope),
                        Json(envelope),
                        None if request is None else Json(request),
                        Json({k: dict(v) for k, v in prompts.items()}) if prompts else None,
                    ),
                ).fetchone()
                if is_turn(envelope) and row is not None:
                    _index_turn(conn, envelope, row[0])
        except errors.UniqueViolation as exc:
            raise FileExistsError(f"run {invocation_id} is already stored") from exc

    def iter_envelopes(self, *, conversation_id: str | None = None) -> Iterator[dict[str, Any]]:
        with self._pool.connection() as conn:
            if conversation_id is None:
                rows = conn.execute("select envelope from runs order by seq").fetchall()
            else:
                rows = conn.execute(
                    "select envelope from runs where conversation_id = %s order by seq",
                    (conversation_id,),
                ).fetchall()
        for (envelope,) in rows:
            yield envelope

    def list_runs(
        self, *, readable: Readable | None = None, limit: int, before: str | None = None
    ) -> Page:
        """A page of runs, newest first, read from the indexes on `runs`."""
        query, params = runs_query(readable=readable, limit=limit, before=before)
        with self._pool.connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return paged(
            [
                (
                    seq,
                    {
                        "invocation_id": invocation_id,
                        "agent_id": agent_id,
                        "status": status,
                        "completed_at": completed_at,
                        "acting_for": acting_for,
                    },
                )
                for seq, invocation_id, agent_id, status, completed_at, acting_for in rows
            ],
            limit,
        )

    def list_conversations(
        self, *, readable: Readable | None = None, limit: int, before: str | None = None
    ) -> Page:
        """A page of conversations, most recently active first, read from
        `conversation_index`."""
        query, params = conversations_query(readable=readable, limit=limit, before=before)
        with self._pool.connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return paged(
            [
                (
                    last_seq,
                    {
                        "conversation_id": conversation_id,
                        "project_id": project_id,
                        "agent_id": agent_id,
                        "first_invocation_id": first_invocation_id,
                        "turns": turns,
                        "started_at": started_at,
                        "last_completed_at": last_completed_at,
                        "last_status": last_status,
                    },
                )
                for (
                    last_seq,
                    conversation_id,
                    project_id,
                    agent_id,
                    first_invocation_id,
                    turns,
                    started_at,
                    last_completed_at,
                    last_status,
                ) in rows
            ],
            limit,
        )

    def get(self, invocation_id: str) -> dict[str, Any] | None:
        return self._column(invocation_id, "envelope")

    def get_request(self, invocation_id: str) -> dict[str, Any] | None:
        return self._column(invocation_id, "request")

    def get_prompts(self, invocation_id: str) -> dict[str, Any]:
        return self._column(invocation_id, "prompts") or {}

    def _column(self, invocation_id: str, column: str) -> dict[str, Any] | None:
        if not RUN_ID.fullmatch(invocation_id):
            return None
        with self._pool.connection() as conn:
            query = sql.SQL("select {} from runs where invocation_id = %s").format(
                sql.Identifier(column)
            )
            row = conn.execute(query, (invocation_id,)).fetchone()
        return None if row is None else row[0]

    def get_schema(self, digest: str) -> dict[str, Any] | None:
        if not DIGEST.fullmatch(digest):
            return None
        with self._pool.connection() as conn:
            row = conn.execute(
                "select schema from run_schemas where digest = %s", (digest,)
            ).fetchone()
        return None if row is None else row[0]

    def put_artifact(self, invocation_id: str, name: str, data: bytes) -> None:
        if not RUN_ID.fullmatch(invocation_id) or artifact_segments(name) is None:
            raise ValueError(f"not an artifact name: {name!r}")
        try:
            with self._pool.connection() as conn, conn.transaction():
                conn.execute(
                    "insert into run_artifacts (invocation_id, name, data) values (%s, %s, %s)",
                    (invocation_id, name, data),
                )
        except errors.ForeignKeyViolation as exc:
            raise KeyError(invocation_id) from exc
        except errors.UniqueViolation as exc:
            raise FileExistsError(f"{invocation_id}: artifact {name} is already kept") from exc

    def get_artifact(self, invocation_id: str, name: str) -> bytes | None:
        if not RUN_ID.fullmatch(invocation_id) or artifact_segments(name) is None:
            return None
        with self._pool.connection() as conn:
            row = conn.execute(
                "select data from run_artifacts where invocation_id = %s and name = %s",
                (invocation_id, name),
            ).fetchone()
        return None if row is None else bytes(row[0])

    def where(self, invocation_id: str) -> str:
        """The database, without a credential, and the run within it."""
        return f"{self._where}#{invocation_id}"


def _index_turn(conn: psycopg.Connection[Any], envelope: dict[str, Any], seq: int) -> None:
    """Count a turn in its conversation's row of `conversation_index`, in the transaction that
    stores it. The first turn makes the row; a later one moves its latest turn on."""
    conn.execute(
        "insert into conversation_index as c (conversation_id, first_invocation_id, project_id,"
        " principal_id, agent_id, turns, started_at, last_seq, last_completed_at, last_status)"
        " values (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s)"
        " on conflict (conversation_id) do update set turns = c.turns + 1,"
        " last_seq = excluded.last_seq, last_completed_at = excluded.last_completed_at,"
        " last_status = excluded.last_status",
        (
            envelope["conversation_id"],
            envelope["invocation_id"],
            envelope.get("project_id"),
            principal_of(envelope),
            envelope["agent_id"],
            envelope["completed_at"],
            seq,
            envelope["completed_at"],
            envelope["outcome"]["status"],
        ),
    )


_RUN_COLUMNS = (
    "seq, invocation_id, envelope ->> 'agent_id', envelope -> 'outcome' ->> 'status',"
    " envelope ->> 'completed_at', envelope -> 'acting_for' ->> 'name'"
)
_CONVERSATION_COLUMNS = (
    "last_seq, conversation_id, project_id, agent_id, first_invocation_id, turns, started_at,"
    " last_completed_at, last_status"
)


def runs_query(
    *, readable: Readable | None, limit: int, before: str | None
) -> tuple[str, dict[str, Any]]:
    """The SQL `list_runs` runs, and its parameters: one row more than a page, newest first."""
    return _page_query("runs", _RUN_COLUMNS, "seq", readable=readable, limit=limit, before=before)


def conversations_query(
    *, readable: Readable | None, limit: int, before: str | None
) -> tuple[str, dict[str, Any]]:
    """The SQL `list_conversations` runs, and its parameters: one row more than a page, the most
    recently active first."""
    return _page_query(
        "conversation_index",
        _CONVERSATION_COLUMNS,
        "last_seq",
        readable=readable,
        limit=limit,
        before=before,
    )


def _page_query(
    table: str,
    columns: str,
    order: str,
    *,
    readable: Readable | None,
    limit: int,
    before: str | None,
) -> tuple[str, dict[str, Any]]:
    """A page of `table` before the cursor, newest first by `order`. Each way a reader may see a
    row is a scan of its own index that stops after a page; a reader's projects are each scanned
    so, and the pages merged. What one page reads is bounded by the page and the reader's
    projects, never by the size of the store."""
    check_limit(limit)
    params: dict[str, Any] = {"end": position(before), "rows": limit + 1}
    page = f"{order} < %(end)s order by {order} desc limit %(rows)s"
    if readable is None:
        return f"select {columns} from {table} where {page}", params
    params["principal"] = readable.principal_id
    if readable.project_ids is None:
        alone = f"select {columns} from {table} where principal_id = %(principal)s and {page}"
        return alone, params
    params["projects"] = sorted(readable.project_ids)
    query = (
        f"select * from ("
        f"(select {columns} from {table}"
        f" where project_id is null and principal_id = %(principal)s and {page})"
        f" union all"
        f" (select found.* from unnest(%(projects)s::text[]) as p (project_id)"
        f" cross join lateral (select {columns} from {table}"
        f" where {table}.project_id = p.project_id and {page}) as found)"
        f") as readable order by {order} desc limit %(rows)s"
    )
    return query, params


def projects_naming_query(principal_id: str) -> tuple[str, dict[str, Any]]:
    """The SQL `projects_naming` runs, and its parameters: the projects with an event naming the
    principal, read from `project_events_by_principal` alone, in the order created. A project's
    first event is its creation, appended in the transaction that creates its row, so the place
    of the first event naming a principal orders the projects as they were created."""
    query = (
        "select project_id from project_events where names_principal = %(principal)s"
        " group by project_id order by min(seq)"
    )
    return query, {"principal": principal_id}


class PostgresSection:
    """A project's exclusive section: a transaction holding the lock on the project's row."""

    def __init__(self, conn: psycopg.Connection[Any], project_id: str) -> None:
        self._conn = conn
        self._project_id = project_id

    def events(self) -> list[dict[str, Any]]:
        return _events(self._conn, self._project_id)

    def append(self, events: list[dict[str, Any]]) -> None:
        _append(self._conn, self._project_id, events)


class PostgresProjectLog(_Pooled):
    """Each project's log and blobs in PostgreSQL."""

    def __init__(self, location: str, *, pool_size: int = DEFAULT_POOL_SIZE) -> None:
        self._where = _open(location)
        self._pool = _pool(self, location, self._where, pool_size)
        # The project of each conversation found so far: a conversation's project never changes
        # once recorded (invariant 12). One not found is looked for again.
        self._conversations: dict[str, str] = {}

    def create(self, project_id: str, event: dict[str, Any]) -> None:
        if not _PROJECT_ID.fullmatch(project_id):
            raise ValueError(f"{project_id!r} is not a project identifier")
        try:
            with self._pool.connection() as conn, conn.transaction():
                conn.execute("insert into projects (project_id) values (%s)", (project_id,))
                _append(conn, project_id, [event])
        except errors.UniqueViolation as exc:
            raise FileExistsError(f"project {project_id} exists") from exc

    def exists(self, project_id: str) -> bool:
        if not _PROJECT_ID.fullmatch(project_id):
            return False
        with self._pool.connection() as conn:
            return _exists(conn, project_id)

    def events(self, project_id: str) -> list[dict[str, Any]]:
        if not _PROJECT_ID.fullmatch(project_id):
            raise KeyError(project_id)
        with self._pool.connection() as conn:
            events = _events(conn, project_id)
        if not events:  # every project's log begins with its creation
            raise KeyError(project_id)
        return events

    @contextmanager
    def section(self, project_id: str) -> Iterator[PostgresSection]:
        """The project's exclusive section. What it appends is committed when it ends without an
        exception, and rolled back if one is raised."""
        if not _PROJECT_ID.fullmatch(project_id):
            raise KeyError(project_id)
        with self._pool.connection() as conn, conn.transaction():
            locked = conn.execute(
                "select 1 from projects where project_id = %s for no key update", (project_id,)
            ).fetchone()
            if locked is None:
                raise KeyError(project_id)
            yield PostgresSection(conn, project_id)

    def keep_blob(self, project_id: str, digest: str, content: bytes) -> None:
        if not _PROJECT_ID.fullmatch(project_id):
            raise KeyError(project_id)
        if not DIGEST.fullmatch(digest):
            raise ValueError("a digest is a SHA-256 in lower-case hex")
        try:
            with self._pool.connection() as conn, conn.transaction():
                conn.execute(
                    "insert into project_blobs (project_id, digest, content) values (%s, %s, %s)"
                    " on conflict (project_id, digest) do nothing",
                    (project_id, digest, content),
                )
        except errors.ForeignKeyViolation as exc:
            raise KeyError(project_id) from exc

    def blob(self, project_id: str, digest: str) -> bytes | None:
        if not _PROJECT_ID.fullmatch(project_id) or not DIGEST.fullmatch(digest):
            return None
        with self._pool.connection() as conn:
            row = conn.execute(
                "select content from project_blobs where project_id = %s and digest = %s",
                (project_id, digest),
            ).fetchone()
        return None if row is None else bytes(row[0])

    def project_of(self, conversation_id: str) -> str | None:
        found = self._conversations.get(conversation_id)
        if found is not None:
            return found
        with self._pool.connection() as conn:
            row = conn.execute(
                "select project_id from project_events where started_conversation = %s"
                " order by seq limit 1",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        project_id: str = row[0]
        self._conversations[conversation_id] = project_id
        return project_id

    def project_ids(self) -> list[str]:
        with self._pool.connection() as conn:
            rows = conn.execute("select project_id from projects order by created").fetchall()
        return [project_id for (project_id,) in rows]

    def projects_naming(self, principal_id: str) -> list[str]:
        query, params = projects_naming_query(principal_id)
        with self._pool.connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [project_id for (project_id,) in rows]

    def where(self) -> str:
        """The database, without a credential."""
        return self._where


def _exists(conn: psycopg.Connection[Any], project_id: str) -> bool:
    row = conn.execute("select 1 from projects where project_id = %s", (project_id,)).fetchone()
    return row is not None


def _events(conn: psycopg.Connection[Any], project_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "select event from project_events where project_id = %s order by seq", (project_id,)
    ).fetchall()
    return [event for (event,) in rows]


def _append(conn: psycopg.Connection[Any], project_id: str, events: list[dict[str, Any]]) -> None:
    """Append `events` on `conn`, in the transaction the caller holds."""
    with conn.cursor() as cur:
        cur.executemany(
            "insert into project_events (project_id, event, started_conversation, names_principal)"
            " values (%s, %s, %s, %s)",
            [
                (
                    project_id,
                    Json(event),
                    event.get("conversation_id")
                    if event.get("event") == _CONVERSATION_STARTED
                    else None,
                    names(event),
                )
                for event in events
            ],
        )

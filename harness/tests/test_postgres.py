"""The PostgreSQL backend passes the storage conformance kit against a real database
(docs/specs/storage.md, "Adding a backend").

Skipped unless `DD_TEST_POSTGRES` names a database the tests may create schemas in, such as
`postgresql://postgres@localhost/postgres`, with any password in libpq's environment
(`PGPASSWORD`), never in the URL. CI names one. Each test keeps its stores in schemas of its own,
dropped afterwards, so tests running side by side do not meet.
"""

from __future__ import annotations

import multiprocessing
import os
import re
import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import quote

import pytest

from dd_harness.listing import Readable, scan_conversations, scan_runs
from dd_harness.projects import Projects
from dd_harness.settings import SettingsError, project_storage, run_storage
from dd_harness.storage import ProjectLog, ProjectStorage, RunStorage
from dd_harness.testing import (
    PROJECT_LOG_CHECKS,
    PROJECT_STORAGE_CHECKS,
    RUN_STORAGE_CHECKS,
    SHARED_RECORD_CHECKS,
    TEST_PRINCIPAL,
)
from dd_harness.testing.storage import stored_envelope

DATABASE = os.environ.get("DD_TEST_POSTGRES", "")

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not DATABASE, reason="no database: DD_TEST_POSTGRES is unset"),
]

psycopg = pytest.importorskip("psycopg")
postgres = pytest.importorskip("dd_harness.postgres")
psycopg_pool = pytest.importorskip("psycopg_pool")

type Locate = Callable[[str], str]


def in_schema(database: str, schema: str) -> str:
    """`database`, with `schema` first on its search path."""
    option = quote(f"-csearch_path={schema}", safe="")
    return f"{database}{'&' if '?' in database else '?'}options={option}"


@pytest.fixture(autouse=True)
def closed_after(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Closes every pool a test's stores open once it ends, so that idle connections do not
    build up while tests run side by side."""
    pools: list[Any] = []
    pool = postgres._pool

    def kept(*args: Any, **kwargs: Any) -> Any:
        pools.append(pool(*args, **kwargs))
        return pools[-1]

    monkeypatch.setattr(postgres, "_pool", kept)
    yield
    for each in pools:
        each.close()


def named(location: str, application: str) -> str:
    """`location`, with its connections named `application` in `pg_stat_activity`."""
    return f"{location}&application_name={application}"


def connections(application: str) -> list[tuple[int, Any]]:
    """The server's connections named `application`: each one's process and when it began."""
    with psycopg.connect(DATABASE, autocommit=True) as conn:
        rows = conn.execute(
            "select pid, backend_start from pg_stat_activity where application_name = %s",
            (application,),
        ).fetchall()
    return sorted((pid, started) for pid, started in rows)


@pytest.fixture
def blank() -> Iterator[Locate]:
    """Opens an empty schema by name, migrating nothing; the same name opens the same one."""
    made: dict[str, str] = {}
    prefix = f"dd_test_{uuid.uuid4().hex[:12]}"

    def locate(name: str) -> str:
        if name not in made:
            schema = f"{prefix}_{re.sub(r'[^a-z0-9]', '_', name.lower())}"
            with psycopg.connect(DATABASE, autocommit=True) as conn:
                conn.execute(f'create schema "{schema}"')
            made[name] = in_schema(DATABASE, schema)
        return made[name]

    yield locate
    with psycopg.connect(DATABASE, autocommit=True) as conn:
        for location in made.values():
            schema = location.rsplit("%3D", 1)[1]
            conn.execute(f'drop schema "{schema}" cascade')


@pytest.fixture
def locate(blank: Locate) -> Locate:
    """Opens a migrated schema by name, as `make` in the conformance kit does."""
    migrated: set[str] = set()

    def located(name: str) -> str:
        location = blank(name)
        if name not in migrated:
            postgres.migrate(location)
            migrated.add(name)
        return location

    return located


@pytest.mark.parametrize("check", RUN_STORAGE_CHECKS.values(), ids=RUN_STORAGE_CHECKS.keys())
def test_the_run_store_keeps_each_guarantee(
    locate: Locate, check: Callable[[Callable[[str], RunStorage]], None]
) -> None:
    check(lambda name: postgres.PostgresRunStore(locate(name)))


@pytest.mark.parametrize("check", PROJECT_LOG_CHECKS.values(), ids=PROJECT_LOG_CHECKS.keys())
def test_the_project_log_keeps_each_guarantee(
    locate: Locate, check: Callable[[Callable[[str], ProjectLog]], None]
) -> None:
    check(lambda name: postgres.PostgresProjectLog(locate(name)))


@pytest.mark.parametrize(
    "check", PROJECT_STORAGE_CHECKS.values(), ids=PROJECT_STORAGE_CHECKS.keys()
)
def test_the_project_rules_keep_each_guarantee_over_the_log(
    locate: Locate, check: Callable[[Callable[[str], ProjectStorage]], None]
) -> None:
    check(lambda name: Projects(postgres.PostgresProjectLog(locate(name))))


@pytest.mark.parametrize("check", SHARED_RECORD_CHECKS.values(), ids=SHARED_RECORD_CHECKS.keys())
def test_logs_over_one_database_contend_for_one_project(
    locate: Locate, check: Callable[[Callable[[str], ProjectLog]], None]
) -> None:
    check(lambda name: postgres.PostgresProjectLog(locate(name)))


def _decide_in_another_process(
    location: str, project_id: str, decision: tuple[str, int, str]
) -> str:
    """Decide on a version through a store of this process's own; says what happened."""
    from dd_harness.postgres import PostgresProjectLog
    from dd_harness.projects import APPROVED, ChangeRefusedError, Decision
    from dd_harness.testing import TEST_PRINCIPAL

    store = Projects(PostgresProjectLog(location))
    try:
        store.decide(
            project_id,
            Decision(*decision, APPROVED),
            acted_for=TEST_PRINCIPAL,
            caused_by="another process",
        )
    except ChangeRefusedError:
        return "refused"
    return "decided"


def test_processes_deciding_on_one_version_admit_one(locate: Locate) -> None:
    """The exclusive section holds across processes, not only threads (issue #522)."""
    from dd_harness.projects import DOCUMENT_CHANGE_REFUSED, DOCUMENT_VERSION_DECIDED
    from dd_harness.testing import TEST_PRINCIPAL
    from dd_harness.testing.storage import drafted_readme

    location = locate("projects")
    store = Projects(postgres.PostgresProjectLog(location))
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    ref = store.record_draft(project_id, drafted_readme())
    (document,) = store.documents(project_id)
    decision = (ref.document_id, ref.version, document["versions"][-1]["digest"])
    processes = 4
    with multiprocessing.get_context("spawn").Pool(processes) as pool:
        outcomes = pool.starmap(
            _decide_in_another_process, [(location, project_id, decision)] * processes
        )
    assert sorted(outcomes) == ["decided"] + ["refused"] * (processes - 1)
    kinds = [e["event"] for e in store.events(project_id)]
    assert kinds.count(DOCUMENT_VERSION_DECIDED) == 1
    assert kinds.count(DOCUMENT_CHANGE_REFUSED) == processes - 1


def test_a_store_refuses_a_schema_not_migrated_and_names_the_command(blank: Locate) -> None:
    location = blank("runs")
    for opened in (postgres.PostgresRunStore, postgres.PostgresProjectLog):
        with pytest.raises(SettingsError, match=r"version 0.*dd-harness storage migrate"):
            opened(location)
    with pytest.raises(SettingsError, match=r"DD_RUNS_DIR .*dd-harness storage migrate"):
        run_storage(location)
    assert postgres.schema_version(location) == 0


def test_migrating_is_explicit_and_can_be_run_again(blank: Locate) -> None:
    location = blank("runs")
    assert postgres.migrate(location)
    assert postgres.schema_version(location) == postgres.SCHEMA_VERSION
    assert postgres.migrate(location) == []
    postgres.PostgresRunStore(location)


def test_a_schema_newer_than_the_build_is_refused(locate: Locate) -> None:
    location = locate("runs")
    with psycopg.connect(location) as conn:
        conn.execute(
            "insert into dd_schema (version, name) values (%s, 'later.sql')",
            (postgres.SCHEMA_VERSION + 1,),
        )
    with pytest.raises(SettingsError, match="dd-harness storage migrate"):
        postgres.PostgresRunStore(location)
    with pytest.raises(SettingsError, match="newer than this build"):
        postgres.migrate(location)


def test_the_settings_choose_the_database_by_its_location(
    locate: Locate, monkeypatch: pytest.MonkeyPatch
) -> None:
    location = locate("store")
    assert isinstance(run_storage(location), postgres.PostgresRunStore)
    projects = project_storage(location)
    assert isinstance(projects, Projects)
    assert isinstance(projects.log, postgres.PostgresProjectLog)


def test_the_pool_size_comes_from_the_settings(
    locate: Locate, monkeypatch: pytest.MonkeyPatch
) -> None:
    location = locate("store")
    store = run_storage(location)
    assert isinstance(store, postgres.PostgresRunStore)
    assert store.pool_size == postgres.DEFAULT_POOL_SIZE
    monkeypatch.setenv("DD_POSTGRES_POOL_SIZE", "3")
    store = run_storage(location)
    assert isinstance(store, postgres.PostgresRunStore)
    assert store.pool_size == 3
    projects = project_storage(location)
    assert isinstance(projects, Projects)
    assert isinstance(projects.log, postgres.PostgresProjectLog)
    assert projects.log.pool_size == 3


def test_a_store_reuses_its_connections_across_calls(locate: Locate) -> None:
    application = f"dd_test_{uuid.uuid4().hex[:12]}"
    store = postgres.PostgresRunStore(named(locate("runs"), application))
    envelope = stored_envelope()
    store.append(envelope)
    kept = connections(application)
    assert kept
    for _ in range(5):
        assert store.has(envelope["invocation_id"])
        assert store.get(envelope["invocation_id"]) == envelope
    assert connections(application) == kept


def test_a_store_keeps_no_more_connections_than_its_pool_size(locate: Locate) -> None:
    """Two sections held at once fill a pool of two; a third call waits for one of them rather
    than opening a connection of its own."""
    application = f"dd_test_{uuid.uuid4().hex[:12]}"
    log = postgres.PostgresProjectLog(named(locate("projects"), application), pool_size=2)
    projects = Projects(log)
    held = [projects.create(acted_for=TEST_PRINCIPAL, caused_by="test") for _ in range(2)]
    entered = threading.Barrier(len(held) + 1)
    release = threading.Event()

    def hold(project_id: str) -> None:
        with log.section(project_id):
            entered.wait()
            release.wait()

    holders = [threading.Thread(target=hold, args=(p,)) for p in held]
    for holder in holders:
        holder.start()
    entered.wait()
    assert len(connections(application)) == 2
    found: list[bool] = []
    waiting = threading.Thread(target=lambda: found.append(log.exists(held[0])))
    waiting.start()
    assert len(connections(application)) == 2
    release.set()
    for thread in (*holders, waiting):
        thread.join()
    assert found == [True]
    assert len(connections(application)) <= 2


def test_closing_a_store_releases_its_connections(locate: Locate) -> None:
    application = f"dd_test_{uuid.uuid4().hex[:12]}"
    with postgres.PostgresProjectLog(named(locate("projects"), application)) as log:
        assert log.project_ids() == []
        assert connections(application)
    assert connections(application) == []
    with pytest.raises(psycopg_pool.PoolClosed):
        log.project_ids()


def test_a_location_names_no_credential(locate: Locate) -> None:
    location = locate("runs")
    store = postgres.PostgresRunStore(location)
    envelope = stored_envelope()
    store.append(envelope)
    where = store.where(envelope["invocation_id"])
    assert where.startswith("postgresql://")
    assert "options" not in where and "@" not in where
    with_password = location.replace("postgresql://", "postgresql://someone:hunter2@", 1)
    for opened in (run_storage, project_storage):
        with pytest.raises(SettingsError, match="password") as refused:
            opened(with_password)
        assert "hunter2" not in str(refused.value)
    with pytest.raises(SettingsError, match="password"):
        run_storage(f"{location}&password=hunter2")


def test_an_unreachable_database_stops_start_up_without_its_credential() -> None:
    with pytest.raises(SettingsError, match=r"DD_PROJECTS_DIR postgresql://127\.0\.0\.1:1/") as e:
        project_storage("postgresql://someone@127.0.0.1:1/nowhere?connect_timeout=2")
    assert "someone" not in str(e.value)


def test_text_is_read_back_as_it_was_stored(locate: Locate) -> None:
    """A document holding any text, an escaped NUL included, comes back as given."""
    store = postgres.PostgresRunStore(locate("runs"))
    envelope = {**stored_envelope(), "note": "nul \u0000, accents é, emoji ✓", "z": 1, "a": 2.5}
    store.append(envelope, {"input": {"text": "\u0000"}}, prompts={"b" * 64: {"x": "\u0000"}})
    assert store.get(envelope["invocation_id"]) == envelope
    assert list(store.get(envelope["invocation_id"]) or {}) == list(envelope)
    assert store.get_request(envelope["invocation_id"]) == {"input": {"text": "\u0000"}}
    assert store.get_prompts(envelope["invocation_id"]) == {"b" * 64: {"x": "\u0000"}}


def test_the_storage_command_migrates_and_reports_the_version(
    blank: Locate, capsys: pytest.CaptureFixture[str]
) -> None:
    from dd_harness.server import main

    location = blank("runs")
    assert main(["storage", "status", location]) == 1
    assert main(["storage", "migrate", location]) == 0
    assert main(["storage", "status", location]) == 0
    shown = capsys.readouterr().out
    assert f"version {postgres.SCHEMA_VERSION}" in shown
    assert "options" not in shown


def test_the_conductor_keeps_a_run_whole_in_the_database(locate: Locate) -> None:
    """A run through the conductor keeps its envelope, request, trace and crate in the database,
    and each is read back through the protocol alone."""
    from dd_harness import testing as fakes
    from dd_harness.storage import CRATE, SPANS
    from dd_harness.testing import TEST_PRINCIPAL, AbstainingStub, make_conductor, request

    conductor = make_conductor(locate("runs"), AbstainingStub(), crate=True)
    env = conductor.invoke(request("stub.abstain", fakes.message()), acting_for=TEST_PRINCIPAL)
    store = postgres.PostgresRunStore(locate("runs"))
    assert store.get(env.invocation_id) == env.to_document()
    assert store.get_request(env.invocation_id) is not None
    assert store.get_artifact(env.invocation_id, SPANS)
    assert store.get_artifact(env.invocation_id, f"{CRATE}/ro-crate-metadata.json")
    assert [e["invocation_id"] for e in store.iter_envelopes()] == [env.invocation_id]


def _at_version_one(location: str) -> None:
    """Apply the first migration alone, as a database made before listing was indexed."""
    _version, name, script = postgres.migrations()[0]
    with psycopg.connect(location) as conn, conn.transaction():
        conn.execute(
            "create table dd_schema (version integer primary key, name text not null,"
            " applied_at timestamptz not null default now())"
        )
        conn.execute(script.encode())
        conn.execute("insert into dd_schema (version, name) values (1, %s)", (name,))


# A store large enough that reading it whole would show in a plan: runs in many conversations,
# some delegated, for many principals, a third of them in projects.
LARGE_STORE = """
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


def test_migrating_indexes_the_runs_already_stored(blank: Locate) -> None:
    """Runs stored before listing was indexed are listed after the migration as they would have
    been stored since."""
    location = blank("runs")
    _at_version_one(location)
    with psycopg.connect(location) as conn:
        conn.execute(LARGE_STORE, {"runs": 2000})
    assert postgres.migrate(location) == [name for _, name, _ in postgres.migrations()[1:]]
    store = postgres.PostgresRunStore(location)
    readable = Readable("principal-7", frozenset({"project-3", "project-21"}))
    for scope in (None, readable, Readable("principal-7", None)):
        scanned = scan_conversations(
            store.iter_envelopes(), readable=scope, limit=10**6, before=None
        )
        assert store.list_conversations(readable=scope, limit=10**6).items == scanned.items
        runs = scan_runs(store.iter_envelopes(), readable=scope, limit=10**6, before=None)
        assert store.list_runs(readable=scope, limit=10**6).items == runs.items


def _scans(plan: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield plan
    for child in plan.get("Plans", []):
        yield from _scans(child)


@pytest.mark.parametrize("listing", ["runs", "conversations"])
def test_a_listing_reads_a_page_not_the_store(blank: Locate, listing: str) -> None:
    """Listing a page, the first or one further on, for any reader, reads index entries in
    proportion to the page and the reader's projects, never to the size of the store
    (docs/specs/storage.md, "Listing")."""
    location = blank("runs")
    _at_version_one(location)
    with psycopg.connect(location) as conn:
        conn.execute(LARGE_STORE, {"runs": 20000})
    postgres.migrate(location)
    with psycopg.connect(location, autocommit=True) as conn:
        conn.execute("analyze")
    store = postgres.PostgresRunStore(location)
    query = postgres.runs_query if listing == "runs" else postgres.conversations_query
    page = store.list_runs if listing == "runs" else store.list_conversations
    limit = 20
    projects = frozenset({"project-3", "project-21", "project-30"})
    for readable in (None, Readable("principal-7", projects), Readable("principal-7", None)):
        first = page(readable=readable, limit=limit)
        assert first.next is not None
        for before in (None, first.next, page(readable=readable, limit=200).next):
            sql, params = query(readable=readable, limit=limit, before=before)
            with psycopg.connect(location) as conn:
                row = conn.execute(f"explain (analyze, format json) {sql}", params).fetchone()
            assert row is not None
            nodes = list(_scans(row[0][0]["Plan"]))
            tables = [n for n in nodes if n.get("Relation Name")]
            assert tables, "the plan reads no table"
            assert not [n for n in tables if n["Node Type"] == "Seq Scan"], tables
            read = sum(
                (n["Actual Rows"] + n.get("Rows Removed by Filter", 0)) * n["Actual Loops"]
                for n in tables
            )
            ways_in = 1 if readable is None or readable.project_ids is None else len(projects) + 1
            assert read <= (limit + 1) * ways_in, (read, nodes)


# Many projects, each created by one of fifty principals, with a few more events each: enough that
# reading every project's log, or every project, would show in a plan.
MANY_PROJECTS = (
    """
insert into projects (project_id)
select '01900000-0000-7000-8000-' || lpad(i::text, 12, '0')
from generate_series(1, %(projects)s) as i
""",
    """
insert into project_events (project_id, event)
select
    '01900000-0000-7000-8000-' || lpad(i::text, 12, '0'),
    json_build_object(
        'event', case when n = 0 then 'project_created' else 'check_event' end,
        'project_id', '01900000-0000-7000-8000-' || lpad(i::text, 12, '0'),
        'acted_for', json_build_object('principal_id', 'principal-' || (i %% 50), 'name', 'P')
    )
from generate_series(1, %(projects)s) as i cross join generate_series(0, 3) as n
order by i, n
""",
)


def _many_projects(location: str, projects: int) -> None:
    with psycopg.connect(location) as conn:
        for statement in MANY_PROJECTS:
            conn.execute(statement, {"projects": projects})


def _project(i: int) -> str:
    return f"01900000-0000-7000-8000-{i:012d}"


def test_migrating_names_the_creators_of_projects_already_stored(blank: Locate) -> None:
    """Projects created before their readers were indexed are found after the migration by
    whoever created them, and by no one who only acted in them."""
    location = blank("projects")
    _at_version_one(location)
    _many_projects(location, 200)
    postgres.migrate(location)
    log = postgres.PostgresProjectLog(location)
    assert log.projects_naming("principal-7") == [_project(i) for i in range(7, 201, 50)]
    assert log.projects_naming("principal-nobody") == []


def test_finding_a_persons_projects_reads_their_projects_not_the_store(blank: Locate) -> None:
    """The projects whose log names a principal are found from an index, reading entries in
    proportion to their projects, never to the number of projects in the store
    (docs/specs/storage.md, "Listing")."""
    location = blank("projects")
    _at_version_one(location)
    _many_projects(location, 20000)
    postgres.migrate(location)
    with psycopg.connect(location, autocommit=True) as conn:
        conn.execute("analyze")
    theirs = 20000 // 50
    assert len(postgres.PostgresProjectLog(location).projects_naming("principal-7")) == theirs
    sql, params = postgres.projects_naming_query("principal-7")
    with psycopg.connect(location) as conn:
        row = conn.execute(f"explain (analyze, format json) {sql}", params).fetchone()
    assert row is not None
    nodes = list(_scans(row[0][0]["Plan"]))
    tables = [n for n in nodes if n.get("Relation Name")]
    assert tables, "the plan reads no table"
    assert not [n for n in tables if n["Node Type"] == "Seq Scan"], tables
    read = sum(
        (n["Actual Rows"] + n.get("Rows Removed by Filter", 0)) * n["Actual Loops"] for n in tables
    )
    assert read <= 2 * theirs, (read, nodes)

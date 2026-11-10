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
import uuid
from collections.abc import Callable, Iterator
from urllib.parse import quote

import pytest

from dd_harness.projects import Projects
from dd_harness.settings import SettingsError, project_storage, run_storage
from dd_harness.storage import ProjectLog, ProjectStorage, RunStorage
from dd_harness.testing import (
    PROJECT_LOG_CHECKS,
    PROJECT_STORAGE_CHECKS,
    RUN_STORAGE_CHECKS,
    SHARED_RECORD_CHECKS,
)
from dd_harness.testing.storage import stored_envelope

DATABASE = os.environ.get("DD_TEST_POSTGRES", "")

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not DATABASE, reason="no database: DD_TEST_POSTGRES is unset"),
]

psycopg = pytest.importorskip("psycopg")
postgres = pytest.importorskip("dd_harness.postgres")

type Locate = Callable[[str], str]


def in_schema(database: str, schema: str) -> str:
    """`database`, with `schema` first on its search path."""
    option = quote(f"-csearch_path={schema}", safe="")
    return f"{database}{'&' if '?' in database else '?'}options={option}"


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

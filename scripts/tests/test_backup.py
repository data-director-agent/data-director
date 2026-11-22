"""deploy/backup.sh and deploy/restore.sh: a deployment's settings, secrets and stores, and the
LiteLLM gateway's database, are backed up, kept for the retention period, and restored into a clean
tree (deploy/README.md, "Backups").

The scripts run against a VM laid out under tmp_path, with a stand-in for systemctl that records
what it is asked. The database round trip runs against the database DD_TEST_POSTGRES names.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import stat
import subprocess
import uuid
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / "deploy" / "backup.sh"
RESTORE = ROOT / "deploy" / "restore.sh"
NAME = re.compile(r"^\d{8}T\d{6}Z$")

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("flock") is None, reason="needs bash and flock"
)


@dataclass
class Host:
    """One VM's directories, and the stand-in systemctl's record of what it was asked."""

    base: Path

    @property
    def etc(self) -> Path:
        return self.base / "etc"

    @property
    def state(self) -> Path:
        return self.base / "state"

    @property
    def broker(self) -> Path:
        return self.base / "broker"

    @property
    def broker_store(self) -> Path:
        return self.broker / "broker.sqlite3"

    @property
    def units(self) -> Path:
        return self.base / "units"

    @property
    def backups(self) -> Path:
        return self.base / "backups"

    @property
    def log(self) -> Path:
        return self.base / "systemctl.log"

    def env(self, systemctl: Path, **extra: str) -> dict[str, str]:
        return {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "DD_ETC": str(self.etc),
            "DD_STATE": str(self.state),
            "DD_BROKER_STATE": str(self.broker),
            "DD_ROOT": str(self.base / "opt"),
            "DD_UNIT_DIR": str(self.units),
            "DD_SYSTEMCTL": str(systemctl),
            "DD_BACKUP_DIR": str(self.backups),
            "SYSTEMCTL_LOG": str(self.log),
            **{k: v for k, v in os.environ.items() if k.startswith("PG")},
            **extra,
        }

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []


@pytest.fixture
def systemctl(tmp_path: Path) -> Path:
    """A systemctl that records each call; the app and the workbench are active. The LiteLLM
    gateway is not installed unless GATEWAY_STATE says it is `active` or `stopped`."""
    path = tmp_path / "systemctl"
    path.write_text(
        "#!/bin/sh\n"
        'echo "$*" >>"$SYSTEMCTL_LOG"\n'
        'case "$*" in "is-active --quiet data-director-llm-gateway.service") '
        '[ "$GATEWAY_STATE" = active ] && exit 0; exit 3;; '
        '"is-enabled --quiet data-director-llm-gateway.service") '
        '[ -n "$GATEWAY_STATE" ] && exit 0; exit 1;; esac\n'
        'case "$*" in "is-active --quiet data-director-app.service"|'
        '"is-active --quiet data-director-workbench.service") exit 0;; "is-active"*) exit 3;; esac\n'
        'case "$*" in "stop "*) [ -n "$SYSTEMCTL_FAIL_STOP" ] && exit 1;; esac\n'
        "exit 0\n"
    )
    path.chmod(0o755)
    return path


def lay_out(host: Host, app_env: str = "", *, broker: bool = True) -> None:
    """A deployment as install.sh leaves it, with something in each store."""
    (host.etc / "credentials" / "app").mkdir(parents=True)
    (host.etc / "app.env").write_text(f"DD_APP_PUBLIC_URL=https://dd.example.ac.uk\n{app_env}")
    (host.etc / "workbench.env").write_text(
        "DD_WORKBENCH_PUBLIC_URL=https://dd.example.ac.uk:8443\n"
    )
    secret = host.etc / "credentials" / "app" / "orcid-client-secret"
    secret.write_text("s3cret")
    secret.chmod(0o600)
    runs = host.state / "runs"
    (runs / "run-1").mkdir(parents=True)
    (runs / "invocations.jsonl").write_text('{"invocation_id": "run-1"}\n')
    (runs / "run-1" / "envelope.json").write_text('{"invocation_id": "run-1"}')
    (host.state / "projects" / "p-1").mkdir(parents=True)
    (host.state / "projects" / "p-1" / "events.jsonl").write_text('{"type": "created"}\n')
    (host.state / "workbench-runs").mkdir()
    (host.state / ".sign-in").write_text("")
    (host.state / ".cache" / "uv").mkdir(parents=True)
    (host.state / ".cache" / "uv" / "big").write_text("not backed up")
    dropin = host.units / "data-director-app.service.d"
    dropin.mkdir(parents=True)
    (dropin / "override.conf").write_text("[Service]\nEnvironment=DD_FEEDBACK_GITHUB_APP_ID=1\n")
    if broker:
        host.broker.mkdir(mode=0o700)
        with closing(sqlite3.connect(host.broker_store)) as db, db:
            db.execute("pragma journal_mode=wal")
            db.execute("create table keys (pseudonym text primary key, sealed blob not null)")
            db.execute("insert into keys values ('p-1', x'00ff')")
        host.broker_store.chmod(0o600)


def broker_rows(store: Path) -> list[tuple[str, bytes]]:
    with closing(sqlite3.connect(store)) as db:
        return db.execute("select pseudonym, sealed from keys order by pseudonym").fetchall()


def run(script: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args], capture_output=True, text=True, check=False, env=env
    )


def backups(host: Host) -> list[Path]:
    if not host.backups.is_dir():
        return []
    return sorted(p for p in host.backups.iterdir() if NAME.match(p.name))


def tree(path: Path) -> dict[str, tuple[bytes, int]]:
    """Each file under `path`, by relative name: its bytes and permission bits."""
    return {
        str(f.relative_to(path)): (f.read_bytes(), stat.S_IMODE(f.stat().st_mode))
        for f in sorted(path.rglob("*"))
        if f.is_file()
    }


@pytest.fixture
def host(tmp_path: Path) -> Host:
    found = Host(tmp_path / "old")
    lay_out(found)
    return found


@pytest.fixture
def clean(tmp_path: Path) -> Host:
    return Host(tmp_path / "new")


def test_a_backup_restores_into_a_clean_tree(host: Host, clean: Host, systemctl: Path) -> None:
    done = run(BACKUP, host.env(systemctl))
    assert done.returncode == 0, done.stderr
    [made] = backups(host)
    assert stat.S_IMODE(made.stat().st_mode) == 0o700
    assert not list(host.backups.glob(".partial-*"))

    done = run(RESTORE, clean.env(systemctl, DD_BACKUP_DIR=""), str(made))
    assert done.returncode == 0, done.stderr
    assert tree(clean.etc) == tree(host.etc)
    for name in ("runs", "projects", "workbench-runs"):
        assert tree(clean.state / name) == tree(host.state / name)
    assert (clean.state / ".sign-in").exists()
    assert not (clean.state / ".cache").exists()
    assert tree(clean.units) == tree(host.units)
    assert broker_rows(clean.broker_store) == broker_rows(host.broker_store)
    assert stat.S_IMODE(clean.broker_store.stat().st_mode) == 0o600
    assert stat.S_IMODE(clean.broker.stat().st_mode) == 0o700
    if os.geteuid() == 0 and run_id("data-director-broker"):
        assert clean.broker_store.owner() == "data-director-broker"
    assert "--domain dd.example.ac.uk" in done.stdout
    assert "data-director-model-broker.service" in done.stdout


def run_id(user: str) -> bool:
    return subprocess.run(["id", user], capture_output=True, check=False).returncode == 0


def test_the_brokers_store_is_copied_while_it_runs(host: Host, systemctl: Path) -> None:
    # The broker holds the store open, with a key it has committed still only in its log.
    with closing(sqlite3.connect(host.broker_store)) as broker:
        broker.execute("pragma wal_autocheckpoint=0")
        with broker:
            broker.execute("insert into keys values ('p-2', x'01')")
        assert Path(f"{host.broker_store}-wal").stat().st_size > 0
        done = run(BACKUP, host.env(systemctl))
        assert done.returncode == 0, done.stderr
        expected = broker_rows(host.broker_store)
    [made] = backups(host)
    assert broker_rows(made / "broker.sqlite3") == expected
    assert ("p-2", b"\x01") in expected
    # One file, with no log left beside it, and checked like every other.
    assert not list(made.glob("broker.sqlite3-*"))
    assert stat.S_IMODE((made / "broker.sqlite3").stat().st_mode) == 0o600
    assert " broker.sqlite3" in (made / "SHA256SUMS").read_text()
    assert f"broker file {host.broker_store} broker.sqlite3" in (made / "MANIFEST").read_text()
    assert not any("model-broker" in call for call in host.calls())


def test_a_deployment_without_the_broker_backs_up_and_restores(
    tmp_path: Path, clean: Host, systemctl: Path
) -> None:
    host = Host(tmp_path / "old")
    lay_out(host, broker=False)
    assert run(BACKUP, host.env(systemctl)).returncode == 0
    [made] = backups(host)
    assert not (made / "broker.sqlite3").exists()
    done = run(RESTORE, clean.env(systemctl), str(made))
    assert done.returncode == 0, done.stderr
    assert not clean.broker.exists()


def test_the_brokers_store_is_set_aside_only_when_forced(host: Host, systemctl: Path) -> None:
    assert run(BACKUP, host.env(systemctl)).returncode == 0
    [made] = backups(host)
    with closing(sqlite3.connect(host.broker_store)) as db, db:
        db.execute("insert into keys values ('p-later', x'02')")
    stale = Path(f"{host.broker_store}-wal")
    stale.write_bytes(b"a log from before the restore")

    done = run(RESTORE, host.env(systemctl), str(made))
    assert done.returncode == 1
    assert "model broker" in done.stderr

    done = run(RESTORE, host.env(systemctl), "--force", str(made))
    assert done.returncode == 0, done.stderr
    assert not stale.exists()
    assert broker_rows(host.broker_store) == [("p-1", b"\x00\xff")]
    [aside] = host.broker.glob("broker.sqlite3.before-restore-*")
    assert ("p-later", b"\x02") in broker_rows(aside)
    assert list(host.broker.glob("broker.sqlite3-wal.before-restore-*"))


def test_the_app_is_stopped_only_while_the_files_are_copied(host: Host, systemctl: Path) -> None:
    assert run(BACKUP, host.env(systemctl)).returncode == 0
    calls = host.calls()
    stop = "stop data-director-app.service data-director-workbench.service"
    start = "start data-director-app.service data-director-workbench.service"
    assert stop in calls and start in calls
    assert calls.index(stop) < calls.index(start)


def test_a_missing_store_stops_nothing_and_leaves_no_backup(host: Host, systemctl: Path) -> None:
    shutil.rmtree(host.state / "projects")
    done = run(BACKUP, host.env(systemctl))
    assert done.returncode == 1
    assert "projects" in done.stderr
    assert backups(host) == []
    assert not list(host.backups.glob(".partial-*"))
    # The stores are checked before anything is stopped.
    assert not any(call.startswith("stop") for call in host.calls())


def test_the_services_are_started_again_when_a_copy_fails(host: Host, systemctl: Path) -> None:
    # A store that cannot be read stops the copy after the services were stopped.
    unreadable = host.state / "runs" / "run-1" / "envelope.json"
    unreadable.chmod(0)
    if os.access(unreadable, os.R_OK):
        pytest.skip("this user reads every file (root)")
    done = run(BACKUP, host.env(systemctl))
    assert done.returncode != 0
    calls = host.calls()
    assert "start data-director-app.service data-director-workbench.service" in calls
    assert backups(host) == []


def test_a_damaged_backup_is_refused_and_nothing_changes(
    host: Host, clean: Host, systemctl: Path
) -> None:
    assert run(BACKUP, host.env(systemctl)).returncode == 0
    [made] = backups(host)
    with (made / "store-runs.tar.gz").open("ab") as archive:
        archive.write(b"x")
    done = run(RESTORE, clean.env(systemctl), str(made))
    assert done.returncode == 1
    assert "checksums" in done.stderr
    assert not clean.base.exists()


def test_a_store_that_holds_something_is_set_aside_only_when_forced(
    host: Host, systemctl: Path
) -> None:
    assert run(BACKUP, host.env(systemctl)).returncode == 0
    [made] = backups(host)
    (host.state / "runs" / "later").write_text("written after the backup")

    done = run(RESTORE, host.env(systemctl), str(made))
    assert done.returncode == 1
    assert "--force" in done.stderr
    assert (host.state / "runs" / "later").exists()

    done = run(RESTORE, host.env(systemctl), "--force", str(made))
    assert done.returncode == 0, done.stderr
    assert not (host.state / "runs" / "later").exists()
    [aside] = host.state.glob("runs.before-restore-*")
    assert (aside / "later").exists()


def test_backups_older_than_the_retention_period_are_deleted(host: Host, systemctl: Path) -> None:
    def stamp(days_ago: int) -> str:
        return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y%m%dT%H%M%SZ")

    host.backups.mkdir(mode=0o700)
    old, recent = host.backups / stamp(8), host.backups / stamp(6)
    for kept in (old, recent, host.backups / ".partial-20000101T000000Z", host.backups / "notes"):
        kept.mkdir()
    done = run(BACKUP, host.env(systemctl, DD_BACKUP_KEEP_DAYS="7"))
    assert done.returncode == 0, done.stderr
    names = {p.name for p in host.backups.iterdir()}
    assert old.name not in names
    assert recent.name in names
    assert "notes" in names
    assert not any(n.startswith(".partial-") for n in names)
    assert len(backups(host)) == 2


def test_the_newest_backup_is_kept_whatever_the_period(host: Host, systemctl: Path) -> None:
    done = run(BACKUP, host.env(systemctl, DD_BACKUP_KEEP_DAYS="1"))
    assert done.returncode == 0, done.stderr
    assert len(backups(host)) == 1


@pytest.mark.parametrize("days", ["0", "a week", "-3"])
def test_a_retention_period_that_is_not_a_number_of_days_is_refused(
    host: Host, systemctl: Path, days: str
) -> None:
    done = run(BACKUP, host.env(systemctl, DD_BACKUP_KEEP_DAYS=days))
    assert done.returncode == 1
    assert "DD_BACKUP_KEEP_DAYS" in done.stderr


# --- A store kept in PostgreSQL -------------------------------------------------------------------

DATABASE = os.environ.get("DD_TEST_POSTGRES", "")


def psql(location: str, sql: str) -> str:
    done = subprocess.run(
        [
            "psql",
            "--no-psqlrc",
            "-qtAX",
            "-v",
            "ON_ERROR_STOP=1",
            f"--dbname={location}",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def _major(version: str) -> int:
    """The major version in `pg_dump --version`, such as 16 in "pg_dump (PostgreSQL) 16.15 (…)"."""
    found = re.search(r"\)\s*(\d+)", version)
    return int(found.group(1)) if found else 0


@pytest.fixture
def databases() -> Iterator[tuple[str, str]]:
    """Two empty databases, the one backed up and the one restored into, dropped afterwards."""
    if not DATABASE:
        pytest.skip("no database: DD_TEST_POSTGRES is unset")
    for tool in ("psql", "pg_dump", "pg_restore"):
        if shutil.which(tool) is None:
            pytest.skip(f"needs {tool}")
    version = subprocess.run(["pg_dump", "--version"], capture_output=True, text=True, check=True)
    server = int(psql(DATABASE, "show server_version_num")) // 10000
    if _major(version.stdout) < server:
        pytest.skip(f"pg_dump is older than the server's major version, {server}")
    names = [f"dd_backup_{uuid.uuid4().hex[:12]}" for _ in range(2)]
    for name in names:
        psql(DATABASE, f'create database "{name}"')
    parts = urlsplit(DATABASE)
    located = [urlunsplit(parts._replace(path=f"/{name}", query="")) for name in names]
    try:
        yield located[0], located[1]
    finally:
        for name in names:
            psql(DATABASE, f'drop database if exists "{name}" with (force)')


@pytest.mark.postgres
def test_a_database_store_restores_into_an_empty_database(
    tmp_path: Path, systemctl: Path, databases: tuple[str, str]
) -> None:
    source, target = databases
    psql(source, "create table runs (seq bigint primary key, envelope json not null)")
    psql(source, """insert into runs values (1, '{"text": "a NUL \\u0000 kept"}'), (2, '{}')""")
    host = Host(tmp_path / "old")
    lay_out(host, app_env=f"DD_RUNS_DIR={source}\nDD_PROJECTS_DIR={source}\n")
    done = run(BACKUP, host.env(systemctl))
    assert done.returncode == 0, done.stderr
    [made] = backups(host)
    assert (made / "db-runs.pgdump").is_file()
    assert not (made / "db-projects.pgdump").exists()
    assert not (made / "store-runs.tar.gz").exists()
    # The workbench's store is still a directory, so the services were stopped for it alone.
    assert (made / "store-workbench-runs.tar.gz").is_file()

    # The clean VM's settings name its own database.
    config = made / "config.tar.gz"
    staged = tmp_path / "staged"
    staged.mkdir()
    subprocess.run(["tar", "-C", str(staged), "-xzf", str(config)], check=True)
    app_env = staged / "app.env"
    app_env.write_text(app_env.read_text().replace(source, target))
    subprocess.run(["tar", "-C", str(staged), "-czf", str(config), "."], check=True)
    subprocess.run(
        ["bash", "-c", "rm SHA256SUMS && sha256sum -- * >SHA256SUMS"], cwd=made, check=True
    )

    clean = Host(tmp_path / "new")
    done = run(RESTORE, clean.env(systemctl), str(made))
    assert done.returncode == 0, done.stderr
    query = "select seq, envelope::text from runs order by seq"
    assert psql(target, query) == psql(source, query)

    again = run(RESTORE, clean.env(systemctl), str(made))
    assert again.returncode == 1
    assert "--force" in again.stderr
    forced = run(RESTORE, clean.env(systemctl), "--force", str(made))
    assert forced.returncode == 0, forced.stderr
    assert psql(target, query) == psql(source, query)


# --- The LiteLLM gateway's database (deploy/gateway-store.sh) --------------------------------------
# A stand-in for docker records what it is asked. The last test runs against the gateway's test
# stack, and is skipped unless DD_TEST_GATEWAY_PROJECT names its compose project; the "LiteLLM
# gateway and model broker" job in CI sets it.

DUMP = "PGDMP gateway"


@pytest.fixture
def docker(tmp_path: Path) -> Path:
    """A docker that records each call. Its gateway runs (DOCKER_DOWN unset): `ps` finds the
    `db` and `litellm` containers, pg_dump writes DUMP (or fails with DOCKER_FAIL_DUMP), the spend
    query answers DOCKER_SPEND, and what pg_restore and psql read is kept in DOCKER_INPUT."""
    path = tmp_path / "docker"
    path.write_text(
        "#!/bin/sh\n"
        'echo "$*" >>"$DOCKER_LOG"\n'
        'case "$*" in\n'
        '  "ps "*service=db) [ -z "$DOCKER_DOWN" ] && echo db-1;;\n'
        '  "ps "*service=litellm) [ -z "$DOCKER_DOWN" ] && echo app-1;;\n'
        '  "exec db-1 pg_dump "*) [ -n "$DOCKER_FAIL_DUMP" ] && exit 1; printf "PGDMP gateway";;\n'
        '  "exec db-1 psql "*) echo "${DOCKER_SPEND:-0}";;\n'
        '  "exec -i db-1 "*) echo "== $4" >>"$DOCKER_INPUT"; cat >>"$DOCKER_INPUT";;\n'
        "esac\n"
        "exit 0\n"
    )
    path.chmod(0o755)
    return path


def env(host: Host, systemctl: Path, docker: Path, **extra: str) -> dict[str, str]:
    return host.env(
        systemctl,
        DD_DOCKER=str(docker),
        DOCKER_LOG=str(host.base / "docker.log"),
        DOCKER_INPUT=str(host.base / "docker.input"),
        **extra,
    )


def docker_calls(host: Host) -> list[str]:
    log = host.base / "docker.log"
    return log.read_text().splitlines() if log.exists() else []


def manifest(made: Path) -> list[str]:
    return (made / "MANIFEST").read_text().splitlines()


def test_a_running_gateway_is_dumped_and_checksummed(
    host: Host, systemctl: Path, docker: Path
) -> None:
    done = run(BACKUP, env(host, systemctl, docker, GATEWAY_STATE="active"))
    assert done.returncode == 0, done.stderr
    [made] = backups(host)
    assert (made / "gateway.pgdump").read_text() == DUMP
    assert "gateway database litellm gateway.pgdump" in manifest(made)
    assert "gateway.pgdump" in (made / "SHA256SUMS").read_text()
    assert any(call.startswith("exec db-1 pg_dump") for call in docker_calls(host))


def test_a_stopped_gateway_is_noted_and_the_rest_is_backed_up(
    host: Host, systemctl: Path, docker: Path
) -> None:
    done = run(BACKUP, env(host, systemctl, docker, GATEWAY_STATE="stopped"))
    assert done.returncode == 0, done.stderr
    [made] = backups(host)
    assert "gateway none" in manifest(made)
    assert not (made / "gateway.pgdump").exists()
    assert (made / "config.tar.gz").exists()
    assert not docker_calls(host)


def test_without_a_gateway_docker_is_not_asked(host: Host, systemctl: Path, docker: Path) -> None:
    done = run(BACKUP, env(host, systemctl, docker))
    assert done.returncode == 0, done.stderr
    [made] = backups(host)
    assert not any(line.startswith("gateway") for line in manifest(made))
    assert not docker_calls(host)


def test_a_failed_dump_leaves_no_backup_and_restarts_what_was_stopped(
    host: Host, systemctl: Path, docker: Path
) -> None:
    done = run(BACKUP, env(host, systemctl, docker, GATEWAY_STATE="active", DOCKER_FAIL_DUMP="1"))
    assert done.returncode == 1
    assert not backups(host)
    assert not list(host.backups.glob(".partial-*"))
    calls = host.calls()
    stops = [i for i, call in enumerate(calls) if call.startswith("stop ")]
    starts = [i for i, call in enumerate(calls) if call.startswith("start ")]
    assert stops and starts and starts[-1] > stops[-1]


@pytest.fixture
def made(host: Host, systemctl: Path, docker: Path) -> Path:
    """A backup that holds the gateway's database, and the password the gateway had."""
    (host.etc / "credentials" / "llm-gateway").mkdir(parents=True)
    (host.etc / "credentials" / "llm-gateway" / "postgres-password").write_text("pa'ss")
    done = run(BACKUP, env(host, systemctl, docker, GATEWAY_STATE="active"))
    assert done.returncode == 0, done.stderr
    [found] = backups(host)
    (host.base / "docker.log").unlink()
    return found


def test_restore_needs_the_gateway_running_and_changes_nothing_without_it(
    clean: Host, systemctl: Path, docker: Path, made: Path
) -> None:
    done = run(RESTORE, env(clean, systemctl, docker, DOCKER_DOWN="1", DD_BACKUP_DIR=""), str(made))
    assert done.returncode == 1
    assert "--gateway" in done.stderr
    assert not clean.etc.exists()
    assert not any(call.startswith("stop ") for call in clean.calls())


def test_restore_refuses_a_gateway_with_spend_unless_forced(
    clean: Host, systemctl: Path, docker: Path, made: Path
) -> None:
    spent = env(clean, systemctl, docker, DOCKER_SPEND="12", DD_BACKUP_DIR="")
    done = run(RESTORE, spent, str(made))
    assert done.returncode == 1
    assert "gateway" in done.stderr
    assert not clean.etc.exists()

    done = run(RESTORE, spent, "--force", str(made))
    assert done.returncode == 0, done.stderr


def test_restore_stops_the_gateway_restores_its_database_and_password(
    clean: Host, systemctl: Path, docker: Path, made: Path
) -> None:
    done = run(RESTORE, env(clean, systemctl, docker, DD_BACKUP_DIR=""), str(made))
    assert done.returncode == 0, done.stderr
    calls = docker_calls(clean)
    stop = calls.index("stop app-1")
    restore = next(i for i, call in enumerate(calls) if " pg_restore " in call)
    assert stop < restore
    # The password reaches psql on its input, quoted, and never on a command line.
    assert not any("pa'ss" in call for call in calls)
    received = (clean.base / "docker.input").read_text()
    assert DUMP in received
    assert "password 'pa''ss'" in received
    assert "data-director-llm-gateway.service" in done.stdout


# --- Against the gateway's test stack ------------------------------------------------------------

PROJECT = os.environ.get("DD_TEST_GATEWAY_PROJECT", "")


def gateway(service: str) -> str:
    found = subprocess.run(
        [
            "docker",
            "ps",
            "-q",
            "--filter",
            f"label=com.docker.compose.project={PROJECT}",
            "--filter",
            f"label=com.docker.compose.service={service}",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert found, f"no running {service} container in {PROJECT}"
    return found[0]


def sql(query: str) -> str:
    return subprocess.run(
        ["docker", "exec", "-i", gateway("db"), "psql", "-U", "litellm", "-d", "litellm", "-qtAX"],
        input=query,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def real_gateway() -> Iterator[str]:
    if not PROJECT or shutil.which("docker") is None:
        pytest.skip("no gateway: DD_TEST_GATEWAY_PROJECT is unset")
    app = gateway("litellm")
    yield app
    # restore.sh leaves the gateway stopped; the test stack is wanted running afterwards.
    subprocess.run(["docker", "start", app], capture_output=True, check=False)


@pytest.mark.gateway
def test_the_gateways_database_round_trips_through_a_backup(
    host: Host, clean: Host, systemctl: Path, real_gateway: str
) -> None:
    keys = 'select token from "LiteLLM_VerificationToken" order by token'
    before = sql(keys)
    assert before, "the test stack has no keys to back up"
    real = {"DD_GATEWAY_PROJECT": PROJECT, "GATEWAY_STATE": "active"}
    done = run(BACKUP, host.env(systemctl, **real))
    assert done.returncode == 0, done.stderr
    [made] = backups(host)
    assert (made / "gateway.pgdump").stat().st_size > 0

    sql('delete from "LiteLLM_VerificationToken"')
    assert sql(keys) != before
    done = run(RESTORE, clean.env(systemctl, DD_BACKUP_DIR="", **real), "--force", str(made))
    assert done.returncode == 0, done.stderr
    assert sql(keys) == before

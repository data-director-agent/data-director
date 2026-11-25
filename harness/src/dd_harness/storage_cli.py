"""`dd-harness storage`: keep the schema of a PostgreSQL run or project storage
(docs/specs/storage.md). The file backends need no migration."""

from __future__ import annotations

import argparse
import sys
from types import ModuleType
from typing import Any

from dd_harness.settings import (
    POSTGRES,
    SettingsError,
    StorageLocation,
    projects_dir,
    redact_location,
    runs_dir,
    storage_location,
)


def _databases(location: str | None) -> list[str]:
    """The databases a storage command acts on: `location`, else each `postgresql://` location
    `DD_RUNS_DIR` and `DD_PROJECTS_DIR` name, once each."""
    named: list[StorageLocation] = []
    if location is not None:
        named.append(storage_location(location, "LOCATION"))
    else:
        for found in (runs_dir, projects_dir):
            try:
                named.append(found())
            except SettingsError:
                continue  # unset: nothing to migrate there
    databases = list(dict.fromkeys(str(n) for n in named if isinstance(n, str)))
    if not databases:
        raise SettingsError(
            f"no {POSTGRES}:// location: name one, or set DD_RUNS_DIR or DD_PROJECTS_DIR to one; "
            "the file backends need no migration (docs/specs/storage.md)"
        )
    return databases


def _postgres() -> ModuleType:
    try:
        import dd_harness.postgres as postgres
    except ImportError:
        sys.exit("dd-harness: storage needs psycopg; install data-director-harness[postgres]")
    return postgres


def cmd_storage_migrate(args: argparse.Namespace) -> int:
    postgres = _postgres()
    for location in _databases(args.location):
        applied = postgres.migrate(location)
        where = redact_location(location)
        done = ", ".join(applied) if applied else "nothing to apply"
        sys.stdout.write(f"{where}: version {postgres.SCHEMA_VERSION} ({done})\n")
    return 0


def cmd_storage_status(args: argparse.Namespace) -> int:
    postgres = _postgres()
    behind = False
    for location in _databases(args.location):
        version = postgres.schema_version(location)
        behind = behind or version != postgres.SCHEMA_VERSION
        sys.stdout.write(
            f"{redact_location(location)}: version {version}, "
            f"this build expects {postgres.SCHEMA_VERSION}\n"
        )
    return 1 if behind else 0


def add_commands(sub: Any) -> None:
    p = sub.add_parser(
        "storage",
        help="keep the schema of a PostgreSQL run or project storage (docs/specs/storage.md)",
    )
    storage = p.add_subparsers(dest="storage_command", required=True)
    for name, func, text in (
        (
            "migrate",
            cmd_storage_migrate,
            "apply the schema changes this build has and the database lacks",
        ),
        (
            "status",
            cmd_storage_status,
            "print the schema version; exits 1 if it is not this build's",
        ),
    ):
        p = storage.add_parser(name, help=text)
        p.add_argument(
            "location",
            nargs="?",
            help="a postgresql:// URL without a password; by default each one DD_RUNS_DIR and "
            "DD_PROJECTS_DIR name",
        )
        p.set_defaults(func=func)

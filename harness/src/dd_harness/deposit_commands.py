"""The `dd-harness project` commands that check a project for deposit and package it
(docs/specs/deposit.md): `confirm-checks` records that the operator confirms the checks before
deposit for the inventory held now, after writing out what they confirm; `validate` checks the
project against the requirements recorded for the repository chosen and keeps the report;
`package` builds the deposit package from a valid project and the runs under `DD_RUNS_DIR`. Each
writes the validation's violations, warnings and notes on stderr. `dd_harness.server` adds them to
its `project` commands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from dd_harness.deposit import PackageRefusedError, Validation, build_package, check
from dd_harness.projects import ProjectError
from dd_harness.projects.deposits import DEPOSIT_CHECKS
from dd_harness.settings import (
    principal_from_env,
    project_storage,
    projects_dir,
    run_storage,
    runs_dir,
)

# What each event a `dd-harness project` command records names as its cause.
CAUSED_BY_COMMAND = "dd-harness project {command}"


def _caused_by(command: str) -> str:
    return CAUSED_BY_COMMAND.format(command=command)


def _write_results(validation: Validation) -> None:
    """Each result of a validation on stderr, violations first."""
    for result in validation.violations:
        sys.stderr.write(f"dd-harness: violation: {result.message}\n")
    for result in validation.warnings:
        sys.stderr.write(f"dd-harness: warning: {result.message}\n")
    for result in validation.notes:
        sys.stderr.write(f"dd-harness: note: {result.message}\n")


def cmd_project_confirm_checks(args: argparse.Namespace) -> int:
    """Record the operator's confirmation of the checks before deposit, each written out first,
    and print the digest of the inventory it is for (docs/specs/deposit.md, invariant 21)."""
    for statement in DEPOSIT_CHECKS:
        sys.stderr.write(f"dd-harness: confirmed: {statement}\n")
    digest = project_storage(projects_dir()).confirm_checks(
        args.project_id,
        acted_for=principal_from_env(),
        caused_by=_caused_by("confirm-checks"),
    )
    sys.stdout.write(digest + "\n")
    return 0


def cmd_project_validate(args: argparse.Namespace) -> int:
    validation, digest = check(
        project_storage(projects_dir()),
        args.project_id,
        acted_for=principal_from_env(),
        caused_by=_caused_by("validate"),
    )
    _write_results(validation)
    sys.stdout.write(digest + "\n")
    return 0 if validation.conforms else 1


def cmd_project_package(args: argparse.Namespace) -> int:
    try:
        package = build_package(
            project_storage(projects_dir()),
            run_storage(runs_dir()),
            args.project_id,
            acted_for=principal_from_env(),
            caused_by=_caused_by("package"),
        )
    except PackageRefusedError as exc:
        _write_results(exc.validation)
        sys.stderr.write("dd-harness: no package was built: the project is not valid for deposit\n")
        return 1
    _write_results(package.validation)
    if args.output:
        try:
            Path(args.output).write_bytes(package.content)
        except OSError as exc:
            raise ProjectError(f"{args.output}: {exc}") from exc
    sys.stdout.write(package.digest + "\n")
    return 0


def add_deposit_commands(project: Any) -> None:
    """Add the deposit commands to the `project` subparsers."""
    p = project.add_parser(
        "confirm-checks",
        help="confirm that ethics approval, data-protection advice and third-party rights were "
        "checked, for the inventory the project holds now; print the inventory's digest",
    )
    p.add_argument("project_id")
    p.set_defaults(func=cmd_project_confirm_checks)
    p = project.add_parser(
        "validate",
        help="check the project against its repository's requirements, keep the report, and "
        "print its digest; exits 1 on a violation",
    )
    p.add_argument("project_id")
    p.set_defaults(func=cmd_project_validate)
    p = project.add_parser(
        "package",
        help="validate the project and, if it is valid, build its deposit package and print its "
        "digest; exits 1 on a violation",
    )
    p.add_argument("project_id")
    p.add_argument("-o", "--output", help="also write the package's zip to this file")
    p.set_defaults(func=cmd_project_package)

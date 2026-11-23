"""`dd-harness case`: export one run, conversation or project as a case for debugging, and check a
case rather than trust it (docs/specs/casefile.md). The stores are those `DD_RUNS_DIR` and, where
set, `DD_PROJECTS_DIR` name; the operator is named by `DD_PRINCIPAL_*`. `--journal` reads this
machine's journal with `journalctl`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from dd_harness import casefile
from dd_harness.project_log import ProjectLog
from dd_harness.settings import (
    principal_from_env,
    project_storage,
    projects_dir,
    run_storage,
    runs_dir,
)


def _project_log() -> ProjectLog | None:
    """The project log, if the deployment keeps projects."""
    if not os.environ.get("DD_PROJECTS_DIR"):
        return None
    return casefile.project_log(project_storage(projects_dir()))


def cmd_export(args: argparse.Namespace) -> int:
    scope, ident = next((s, getattr(args, s)) for s in casefile.SCOPES if getattr(args, s))
    options = casefile.Options(
        content="named" if args.content_named else "carried",
        journal=casefile.read_journal if args.journal else None,
    )
    try:
        digest = casefile.export(
            Path(args.output),
            run_storage(runs_dir()),
            _project_log(),
            scope,
            ident,
            principal_from_env(),
            options,
        )
    except (LookupError, OSError) as exc:
        sys.stderr.write(f"dd-harness case export: {exc}\n")
        return 2
    sys.stdout.write(f"{args.output}\ncase.json sha256:{digest}\n")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    report = casefile.verify(Path(args.case))
    sys.stdout.write(report.summary() + "\n")
    return 0 if report.passed else 1


def add_commands(sub: Any) -> None:
    p = sub.add_parser(
        "case", help="export a run, conversation or project for debugging (docs/specs/casefile.md)"
    )
    case = p.add_subparsers(dest="case_command", required=True)
    p = case.add_parser(
        "export",
        help="write a case, a directory or a .zip, and print the digest of its case.json",
    )
    which = p.add_mutually_exclusive_group(required=True)
    which.add_argument("--run", help="a run and every run delegated from it")
    which.add_argument("--conversation", help="every turn of a conversation and its children")
    which.add_argument("--project", help="a project's log, its content and all its runs")
    p.add_argument("-o", "--output", required=True, help="a new directory, or a file ending .zip")
    p.add_argument(
        "--content-named",
        action="store_true",
        help="write every text as its ni: digest, for a case that must leave the institution",
    )
    p.add_argument(
        "--journal",
        action="store_true",
        help="keep the deployment's journal lines that name the case (runs journalctl)",
    )
    p.set_defaults(func=cmd_export)
    p = case.add_parser("verify", help="check a case; exits 1 if a check fails")
    p.add_argument("case", help="a case directory or zip")
    p.set_defaults(func=cmd_verify)

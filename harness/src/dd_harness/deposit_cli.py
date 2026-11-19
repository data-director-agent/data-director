"""`dd-harness project review`, `decide-item` and `confirm-checks`: the pause before packaging
from the command line (`dd_harness.deposit_review`, docs/specs/deposit.md).

`review` prints what the deposit check asks a person to decide, as JSON. `decide-item` records the
operator's decision on one item by its identifier, and `confirm-checks` their confirmation of the
checks before deposit, after printing the statements they confirm. Each acts for the operator's
principal, as every `dd-harness project` command does (`dd_harness.server`).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from dd_harness.deposit_review import CONFIRMATIONS, ItemDecision, confirm, decide_item, review
from dd_harness.settings import principal_from_env, project_storage, projects_dir

CAUSED_BY = "dd-harness project {command}"


def cmd_review(args: argparse.Namespace) -> int:
    found = review(project_storage(projects_dir()), args.project_id)
    sys.stdout.write(json.dumps(found.to_document(), indent=2, ensure_ascii=False) + "\n")
    return 1 if found.paused else 0


def cmd_decide_item(args: argparse.Namespace) -> int:
    item = decide_item(
        project_storage(projects_dir()),
        args.project_id,
        args.item_id,
        ItemDecision(args.decision),
        args.note,
        acted_for=principal_from_env(),
        caused_by=CAUSED_BY.format(command="decide-item"),
    )
    sys.stdout.write(f"{item.path}: {args.decision}\n")
    return 0


def cmd_confirm_checks(args: argparse.Namespace) -> int:
    for text in CONFIRMATIONS.values():
        sys.stdout.write(f"Confirmed: {text}\n")
    confirm(
        project_storage(projects_dir()),
        args.project_id,
        CONFIRMATIONS,
        acted_for=principal_from_env(),
        caused_by=CAUSED_BY.format(command="confirm-checks"),
    )
    return 0


def add_commands(project: Any) -> None:
    """Add the commands to `dd-harness project`'s subparsers."""
    p = project.add_parser(
        "review",
        help="print, as JSON, what a person must decide and confirm before packaging; exits 1 "
        "while anything is open",
    )
    p.add_argument("project_id")
    p.set_defaults(func=cmd_review)
    p = project.add_parser(
        "decide-item", help="record your decision on an item the deposit check lists"
    )
    p.add_argument("project_id")
    p.add_argument("item_id", help="the item's identifier, as `review` prints it")
    p.add_argument("decision", choices=[d.value for d in ItemDecision])
    p.add_argument("--note", help="why, or what was changed")
    p.set_defaults(func=cmd_decide_item)
    p = project.add_parser(
        "confirm-checks",
        help="confirm that ethics approval, data protection advice and third-party rights have "
        "been checked",
    )
    p.add_argument("project_id")
    p.set_defaults(func=cmd_confirm_checks)

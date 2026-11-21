"""`dd-harness project members`, `member-add`, `member-role` and `member-remove`: a project's
members from the command line (`dd_harness.projects.membership`, docs/specs/projects.md).

`members` prints each member, their role and since when, as JSON lines. An owner adds a person by
the principal identifier they sign in with: a bare ORCID iD is taken as its `https://orcid.org/`
IRI. Each command acts for the operator's principal, as every `dd-harness project` command does
(`dd_harness.server`), and is refused unless that principal may do it (`dd_harness.project_access`):
an owner manages members, and any member may remove themselves.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from dd_harness import project_access
from dd_harness.orcid import ORCID_ID
from dd_harness.project_access import Action
from dd_harness.projects import MEMBER, MEMBER_ROLES, ProjectError, UnknownProjectError
from dd_harness.settings import principal_from_env, project_storage, projects_dir
from dd_harness.storage import ProjectStorage
from dd_sdk.contract.models import Principal

CAUSED_BY = "dd-harness project {command}"
ORCID_IRI = "https://orcid.org/{}"


def member_id(given: str) -> str:
    """The principal identifier `given` names: a bare ORCID iD as its IRI, else as given."""
    given = given.strip()
    return ORCID_IRI.format(given) if ORCID_ID.fullmatch(given) else given


def _refused(project_id: str) -> ProjectError:
    return ProjectError(f"you may not change the members of project {project_id!r}")


def _managed(project_id: str) -> tuple[ProjectStorage, Principal]:
    """The store and the operator's principal, if they may manage the project's members."""
    store, principal = project_storage(projects_dir()), principal_from_env()
    if not project_access.may(store, project_id, principal, Action.MANAGE):
        raise _refused(project_id)
    return store, principal


def cmd_members(args: argparse.Namespace) -> int:
    store = project_storage(projects_dir())
    if not project_access.may(store, args.project_id, principal_from_env(), Action.READ):
        raise UnknownProjectError(f"no project {args.project_id!r}")
    for member in store.members(args.project_id):
        sys.stdout.write(json.dumps(member, ensure_ascii=False) + "\n")
    return 0


def cmd_member_add(args: argparse.Namespace) -> int:
    store, principal = _managed(args.project_id)
    store.add_member(
        args.project_id,
        member_id(args.member),
        args.role,
        acted_for=principal,
        caused_by=CAUSED_BY.format(command="member-add"),
    )
    return 0


def cmd_member_role(args: argparse.Namespace) -> int:
    store, principal = _managed(args.project_id)
    store.change_role(
        args.project_id,
        member_id(args.member),
        args.role,
        acted_for=principal,
        caused_by=CAUSED_BY.format(command="member-role"),
    )
    return 0


def cmd_member_remove(args: argparse.Namespace) -> int:
    store, principal = project_storage(projects_dir()), principal_from_env()
    member = member_id(args.member)
    if not project_access.may_remove_member(store, args.project_id, principal, member):
        raise _refused(args.project_id)
    store.remove_member(
        args.project_id,
        member,
        acted_for=principal,
        caused_by=CAUSED_BY.format(command="member-remove"),
    )
    return 0


def add_commands(project: Any) -> None:
    """Add the commands to `dd-harness project`'s subparsers."""
    p = project.add_parser("members", help="print the project's members and roles as JSONL")
    p.add_argument("project_id")
    p.set_defaults(func=cmd_members)
    p = project.add_parser("member-add", help="add a person to the project by ORCID iD")
    p.add_argument("project_id")
    p.add_argument("member", help="an ORCID iD, or the principal identifier they sign in with")
    p.add_argument("--role", choices=MEMBER_ROLES, default=MEMBER)
    p.set_defaults(func=cmd_member_add)
    p = project.add_parser("member-role", help="change a member's role")
    p.add_argument("project_id")
    p.add_argument("member", help="an ORCID iD, or the member's principal identifier")
    p.add_argument("role", choices=MEMBER_ROLES)
    p.set_defaults(func=cmd_member_role)
    p = project.add_parser("member-remove", help="remove a member, or leave by naming yourself")
    p.add_argument("project_id")
    p.add_argument("member", help="an ORCID iD, or the member's principal identifier")
    p.set_defaults(func=cmd_member_remove)

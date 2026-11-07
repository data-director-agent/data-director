"""The harness's own server: the conductor over A2A, and nothing else (#55, docs/specs/system.md).

`dd-harness serve` is for deployments. It serves the A2A JSON-RPC endpoint and the agent card, with
no viewer, AG-UI, run index, test kit or Inspect AI. Other systems call it: an app, another Data
Director instance, or a delegation agent calling back under its grant (docs/specs/orchestration.md).
`workbench serve` builds the same conductor with `serving` and adds its own routes.

Every setting comes from the real environment (`Settings.from_env()` with no defaults): an unset
`DD_PROFILE`, `DD_AGENTS_CONFIG`, `DD_SOURCES_CONFIG`, `DD_RUNS_DIR` or principal stops start-up.
No `.env` file is read.

`dd-harness project` keeps a project's record under `DD_PROJECTS_DIR` for the operator's principal
(docs/specs/projects.md): `create`, `add-inventory` for a `FileInventory` that `dd-inventory` wrote,
`choose-repository` with the requirement sets under `DD_REPOSITORIES_DIR` (docs/specs/deposit.md),
`validate` against the requirements recorded for the repository chosen, `package` to build the
deposit package from a valid project and the runs under `DD_RUNS_DIR`, and `events`.

There is no authentication of callers yet (docs/specs/policy-and-identity.md, #17, #43): every
invocation acts for the operator's principal, whoever sent it. Do not expose this server beyond a
trusted network.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from starlette.applications import Starlette

from dd_harness.conductor import Conductor
from dd_harness.deposit import PackageRefusedError, Validation, build_package, check
from dd_harness.identity import Authenticator, IdentityError, OperatorAssertion
from dd_harness.policy import PolicyError
from dd_harness.projects import ProjectError
from dd_harness.registry import RegistryError
from dd_harness.requirements import RequirementsError, load_requirements
from dd_harness.settings import (
    Settings,
    SettingsError,
    build_authenticator,
    build_conductor,
    principal_from_env,
    project_storage,
    projects_dir,
    repositories_dir,
    run_storage,
    runs_dir,
)
from dd_harness.sources import SourceConfigError
from dd_harness.transport.a2a import a2a_routes

# Hosts that are reachable from this machine only; any other prints the warning below.
LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})
UNTRUSTED_WARNING = (
    "dd-harness: warning: serving on {host}. Callers are not authenticated, so every "
    "invocation acts for the configured principal; expose this server to a trusted network "
    "only, or set DD_OIDC_ISSUER to sign callers in.\n"
)


def serving(settings: Settings, base_url: str) -> tuple[Conductor, Authenticator]:
    """A conductor and authenticator for a server reached at `base_url`.

    The conductor's delegation callback is `DD_HARNESS_URL` if set, else `base_url`
    (docs/specs/orchestration.md). An unset principal or a missing or malformed file raises here,
    before anything is served."""
    authenticator = build_authenticator(settings)
    conductor = build_conductor(settings)
    conductor.harness_url = settings.harness_url or base_url
    return conductor, authenticator


def build_app(conductor: Conductor, authenticator: Authenticator, base_url: str) -> Starlette:
    """The A2A endpoint at `/a2a` and the agent card at `/.well-known/agent-card.json`."""
    _card, routes = a2a_routes(conductor, authenticator, base_url)
    return Starlette(routes=routes)


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        sys.exit("dd-harness: serve needs uvicorn; install data-director-harness[serve]")

    settings = Settings.from_env()
    # The address other systems reach the harness by. Binding all interfaces is no such address,
    # so a deployment behind a proxy or a container network sets DD_HARNESS_URL.
    base_url = settings.harness_url or f"http://{args.host}:{args.port}"
    conductor, authenticator = serving(settings, base_url)
    if args.host not in LOOPBACK and isinstance(authenticator, OperatorAssertion):
        sys.stderr.write(UNTRUSTED_WARNING.format(host=args.host))
    try:
        uvicorn.run(build_app(conductor, authenticator, base_url), host=args.host, port=args.port)
    finally:
        conductor.close()
    return 0


# What a project event names as its cause when a person ran a command (docs/specs/projects.md).
CAUSED_BY_COMMAND = "dd-harness project {command}"


def cmd_project_create(args: argparse.Namespace) -> int:
    store = project_storage(projects_dir())
    project_id = store.create(
        acted_for=principal_from_env(),
        caused_by=CAUSED_BY_COMMAND.format(command="create"),
        title=args.title,
    )
    sys.stdout.write(project_id + "\n")
    return 0


def cmd_project_list(args: argparse.Namespace) -> int:
    for summary in project_storage(projects_dir()).projects():
        sys.stdout.write(json.dumps(summary, ensure_ascii=False) + "\n")
    return 0


def cmd_project_add_inventory(args: argparse.Namespace) -> int:
    store = project_storage(projects_dir())
    try:
        inventory = json.loads(Path(args.file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"{args.file}: {exc}") from exc
    if not isinstance(inventory, dict):
        raise ProjectError(f"{args.file}: not a JSON object")
    digest = store.add_inventory(
        args.project_id,
        inventory,
        acted_for=principal_from_env(),
        caused_by=CAUSED_BY_COMMAND.format(command="add-inventory"),
    )
    sys.stdout.write(digest + "\n")
    return 0


def cmd_project_choose_repository(args: argparse.Namespace) -> int:
    store = project_storage(projects_dir())
    resolved = load_requirements(repositories_dir()).resolve(args.re3data, args.name, args.standard)
    digest = store.choose_repository(
        args.project_id,
        resolved,
        acted_for=principal_from_env(),
        caused_by=CAUSED_BY_COMMAND.format(command="choose-repository"),
    )
    for warning in resolved.warnings:
        sys.stderr.write(f"dd-harness: warning: {warning}\n")
    sys.stdout.write(digest + "\n")
    return 0


def cmd_project_choose_entry(args: argparse.Namespace) -> int:
    project_storage(projects_dir()).choose_entry(
        args.project_id,
        args.entry,
        acted_for=principal_from_env(),
        caused_by=CAUSED_BY_COMMAND.format(command="choose-entry"),
    )
    return 0


def cmd_project_mark_step(args: argparse.Namespace) -> int:
    project_storage(projects_dir()).mark_step(
        args.project_id,
        args.step_id,
        args.mark,
        acted_for=principal_from_env(),
        caused_by=CAUSED_BY_COMMAND.format(command="mark-step"),
    )
    return 0


def _write_results(validation: Validation) -> None:
    """Each result of a validation on stderr, violations first."""
    for result in validation.violations:
        sys.stderr.write(f"dd-harness: violation: {result.message}\n")
    for result in validation.warnings:
        sys.stderr.write(f"dd-harness: warning: {result.message}\n")


def cmd_project_validate(args: argparse.Namespace) -> int:
    validation, digest = check(
        project_storage(projects_dir()),
        args.project_id,
        acted_for=principal_from_env(),
        caused_by=CAUSED_BY_COMMAND.format(command="validate"),
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
            caused_by=CAUSED_BY_COMMAND.format(command="package"),
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


def cmd_project_events(args: argparse.Namespace) -> int:
    for event in project_storage(projects_dir()).events(args.project_id):
        sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dd-harness",
        description="Data Director harness: serve the conductor over A2A, and keep projects",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="serve the A2A endpoint and the agent card")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser(
        "project", help="keep a project's record under DD_PROJECTS_DIR (docs/specs/projects.md)"
    )
    project = p.add_subparsers(dest="project_command", required=True)
    p = project.add_parser("create", help="create a project and print its identifier")
    p.add_argument("--title", help="a name that tells the project apart from others")
    p.set_defaults(func=cmd_project_create)
    p = project.add_parser("list", help="print a summary of every project, as JSONL")
    p.set_defaults(func=cmd_project_list)
    p = project.add_parser(
        "add-inventory", help="add a FileInventory that dd-inventory wrote, and print its digest"
    )
    p.add_argument("project_id")
    p.add_argument("file", help="the inventory's JSON file")
    p.set_defaults(func=cmd_project_add_inventory)
    p = project.add_parser(
        "choose-repository",
        help="record the repository chosen, and print the digest of its requirements",
    )
    p.add_argument("project_id")
    p.add_argument("--re3data", required=True, help="the repository's re3data identifier")
    p.add_argument("--name", required=True, help="the repository's name")
    p.add_argument(
        "--standard",
        action="append",
        default=[],
        help="a metadata standard its re3data record declares, as re3data names it; repeatable",
    )
    p.set_defaults(func=cmd_project_choose_repository)
    p = project.add_parser(
        "choose-entry", help="record the Blueprint entry point the researcher is at (1, 2 or 3)"
    )
    p.add_argument("project_id")
    p.add_argument("entry", type=int, choices=(1, 2, 3))
    p.set_defaults(func=cmd_project_choose_entry)
    p = project.add_parser(
        "mark-step",
        help="mark a process-flow step done, skipped or open again (docs/specs/orchestration.md)",
    )
    p.add_argument("project_id")
    p.add_argument("step_id", help="a step id, such as governance.embargo")
    p.add_argument("mark", choices=("done", "skipped", "open"))
    p.set_defaults(func=cmd_project_mark_step)
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
    p = project.add_parser("events", help="print the project's events, oldest first, as JSONL")
    p.add_argument("project_id")
    p.set_defaults(func=cmd_project_events)

    args = parser.parse_args(argv)
    try:
        result: int = args.func(args)
    # No principal (docs/specs/policy-and-identity.md), a path the deployment must name
    # (docs/specs/system.md), or a profile, agent list or source list that is missing or malformed:
    # nothing may be served. An unknown project, an inventory its class schema refuses, or
    # requirement sets that are malformed or contradict one another, change nothing.
    except (
        IdentityError,
        SettingsError,
        PolicyError,
        RegistryError,
        SourceConfigError,
        ProjectError,
        RequirementsError,
    ) as exc:
        sys.exit(f"dd-harness: {exc}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

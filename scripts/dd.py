# /// script
# requires-python = ">=3.14"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Configure and check a Data Director instance, in development or on a VM.

    uv run scripts/dd.py setup     # development: ask for your settings, write them, install, build
    uv run scripts/dd.py start     # development: the agents, the app and the shell's dev server
    uv run scripts/dd.py doctor    # check everything and name the fix for each problem; changes nothing
    uv run scripts/dd.py apply     # make the instance what deployment.yaml says (--check: only say)
    uv run scripts/dd.py edit      # edit deployment.yaml, checked before it is saved, then apply it
    uv run scripts/dd.py secret set AGENT SECRET | remove AGENT SECRET | list
    uv run scripts/dd.py backup    # VM: back up the settings, secrets and stores now
    uv run scripts/dd.py restore [--force] BACKUP   # VM: put a backup back (deploy/README.md)
    uv run scripts/dd.py new-agent NAME             # development: write and register a new agent

On a VM deployed with deploy/install.sh, which installs this as `data-director`:

    sudo data-director doctor
    sudo data-director secret set orchestrator-model anthropic-api-key
    sudo data-director edit      # orchestrator: model; checks it, then offers to apply it

`deployment.yaml` says what an instance runs: its name, the orchestrator (model or stub) and any
agents disabled (scripts/ddtool/deployment.py). `apply` writes the rest from it.

The target is the VM when /etc/data-director and /opt/data-director exist, else development;
`--target` chooses. Development's settings are in `config/local/`, which mirrors
/etc/data-director/ (docs/guide/operations/configuration.md): `app.env` (the app's),
`agents.env` (every agent's), `agents/<name>.env` (one agent's own) and `credentials/` (secrets,
each named by a `*_FILE` variable in the agent's own file, never in a file every agent reads).

`setup` and `start` are a development convenience. The app and the harness stay as strict as
they are: only `start` falls back to the example principal when none is set, and it says so. It
reads the agents and their ports from `app/config/agents.yaml`; agent `<name>` is served by
`dd-<name>`. POSIX only; on Windows, use WSL.

Each command is a module of `scripts/ddtool/`; this file only reads the command line.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from ddtool import paths
from ddtool.backup import run_script
from ddtool.common import DevError
from ddtool.deployment import Place, apply
from ddtool.doctor import doctor
from ddtool.edit import edit
from ddtool.new_agent import new_agent
from ddtool.secret import secret
from ddtool.setup import Prompter, setup
from ddtool.start import start
from ddtool.vm import System, Vm, detect
from ddtool.vm_doctor import vm_doctor


def _parser() -> argparse.ArgumentParser:
    """The command line: each command, with the options it takes."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--target",
        choices=["dev", "vm"],
        help="development (config/local/) or a VM (/etc/data-director); found by default",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    setup_cmd = commands.add_parser(
        "setup", help="development: ask for your settings, write them, install and build"
    )
    setup_cmd.add_argument("--yes", action="store_true", help="accept every default without asking")
    setup_cmd.add_argument("--no-install", action="store_true", help="write the settings only")
    start_cmd = commands.add_parser(
        "start", help="development: run the agents, the app and the shell's dev server"
    )
    start_cmd.add_argument(
        "--agents-only", action="store_true", help="only the agents (for the workbench)"
    )
    start_cmd.add_argument(
        "--no-web", action="store_true", help="no Vite dev server; use the built shell"
    )
    start_cmd.add_argument(
        "--no-reload", action="store_true", help="do not restart an agent when its files change"
    )
    doctor_cmd = commands.add_parser(
        "doctor", help="check everything and name each fix; change nothing"
    )
    doctor_cmd.add_argument(
        "--json",
        action="store_true",
        help="on a VM, print the report as one JSON document (what the admin service reads)",
    )
    apply_cmd = commands.add_parser(
        "apply", help="make the instance what deployment.yaml says: profile, units, credentials"
    )
    apply_cmd.add_argument(
        "--check", action="store_true", help="say what would change, change nothing"
    )
    edit_cmd = commands.add_parser(
        "edit", help="edit deployment.yaml, check it before saving it, then offer to apply it"
    )
    after_edit = edit_cmd.add_mutually_exclusive_group()
    after_edit.add_argument(
        "--apply", dest="apply_now", action="store_true", default=None, help="apply without asking"
    )
    after_edit.add_argument(
        "--no-apply", dest="apply_now", action="store_false", help="only save the file"
    )
    secret_cmd = commands.add_parser(
        "secret", help="set, remove or list an agent's secrets, such as its model key"
    )
    secret_cmd.add_argument("args", nargs=argparse.REMAINDER, metavar="set|remove|rm|list ...")
    commands.add_parser(
        "backup", help="VM: back up the settings, secrets and stores now (deploy/README.md)"
    )
    restore_cmd = commands.add_parser(
        "restore", help="VM: put a backup back, before deploy/install.sh starts it all again"
    )
    restore_cmd.add_argument(
        "--force", action="store_true", help="set aside or replace stores that hold something"
    )
    restore_cmd.add_argument("backup", help="the backup's directory, such as /var/backups/...")
    new_agent_cmd = commands.add_parser(
        "new-agent", help="development: write a new agent from the template and register it"
    )
    new_agent_cmd.add_argument(
        "name", help="its directory under agents/, such as advisor-foo (agent id advisor.foo)"
    )
    return parser


def _apply(target: str, args: argparse.Namespace) -> int:
    vm = Vm()
    place = Place.vm(vm) if target == "vm" else Place.dev()
    return apply(System(), place, vm if target == "vm" else None, check=args.check)


def _edit(target: str, args: argparse.Namespace) -> int:
    vm = Vm()
    place = Place.vm(vm) if target == "vm" else Place.dev()
    return edit(System(), place, vm if target == "vm" else None, apply_now=args.apply_now)


def _doctor(target: str, args: argparse.Namespace) -> int:
    if target == "vm":
        return vm_doctor(as_json=args.json)
    if args.json:
        raise DevError("doctor --json reports on a VM; run it there, or without --json")
    return doctor()


# Each command, as a function of the target and the parsed arguments.
COMMANDS: dict[str, Callable[[str, argparse.Namespace], int]] = {
    "new-agent": lambda _target, args: new_agent(paths.ROOT, args.name),
    "setup": lambda _target, args: setup(
        Prompter(accept_defaults=args.yes), install=not args.no_install
    ),
    "start": lambda _target, args: start(
        agents_only=args.agents_only, web=not args.no_web, reload=not args.no_reload
    ),
    "backup": lambda target, _args: run_script(target, "backup", []),
    "restore": lambda target, args: run_script(
        target, "restore", [*(["--force"] if args.force else []), args.backup]
    ),
    "secret": lambda target, args: secret(target, args.args),
    "apply": _apply,
    "edit": _edit,
    "doctor": _doctor,
}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    target = args.target or ("vm" if detect(System(), Vm()) else "dev")
    try:
        if args.command in {"setup", "start", "new-agent"} and target == "vm":
            raise DevError(
                f"`{args.command}` is for development; on a VM, deploy/install.sh sets it up "
                "and systemd runs it (deploy/README.md)"
            )
        return COMMANDS[args.command](target, args)
    except DevError as exc:
        print(f"dd.py: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt, EOFError:
        print()
        return 130


if __name__ == "__main__":
    sys.exit(main())

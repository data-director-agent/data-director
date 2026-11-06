# /// script
# requires-python = ">=3.14"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Configure and check a Data Director instance, in development or on a VM.

    uv run scripts/dd.py setup     # development: ask for your settings, write them, install, build
    uv run scripts/dd.py start     # development: the agents, the app and the shell's dev server
    uv run scripts/dd.py doctor    # check everything and name the fix for each problem; changes nothing
    uv run scripts/dd.py secret set AGENT SECRET | remove AGENT SECRET | list

On a VM deployed with deploy/install.sh, which installs this as `data-director`:

    sudo data-director doctor
    sudo data-director secret set orchestrator-model anthropic-api-key

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

from ddtool.common import DevError
from ddtool.doctor import doctor
from ddtool.secret import secret
from ddtool.setup import Prompter, setup
from ddtool.start import start
from ddtool.vm import System, Vm, detect
from ddtool.vm_doctor import vm_doctor


def main(argv: list[str] | None = None) -> int:
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
    commands.add_parser("doctor", help="check everything and name each fix; change nothing")
    secret_cmd = commands.add_parser(
        "secret", help="set, remove or list an agent's secrets, such as its model key"
    )
    secret_cmd.add_argument("args", nargs=argparse.REMAINDER, metavar="set|remove|list ...")
    args = parser.parse_args(argv)
    target = args.target or ("vm" if detect(System(), Vm()) else "dev")
    try:
        if args.command in {"setup", "start"} and target == "vm":
            raise DevError(
                f"`{args.command}` is for development; on a VM, deploy/install.sh sets it up "
                "and systemd runs it (deploy/README.md)"
            )
        if args.command == "setup":
            return setup(Prompter(accept_defaults=args.yes), install=not args.no_install)
        if args.command == "start":
            return start(
                agents_only=args.agents_only, web=not args.no_web, reload=not args.no_reload
            )
        if args.command == "secret":
            return secret(target, args.args)
        return vm_doctor() if target == "vm" else doctor()
    except DevError as exc:
        print(f"dd.py: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt, EOFError:
        print()
        return 130


if __name__ == "__main__":
    sys.exit(main())

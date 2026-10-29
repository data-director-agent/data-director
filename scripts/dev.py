# /// script
# requires-python = ">=3.14"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Set up and run the Data Director development stack from one terminal.

    uv run scripts/dev.py setup     # asks for your settings, writes them, installs, builds
    uv run scripts/dev.py start     # the agents, the app and the shell's dev server; Ctrl-C stops all
    uv run scripts/dev.py doctor    # checks the toolchain, the settings and the ports; changes nothing

`setup` writes each setting where it belongs, so nobody has to edit a settings file by hand:

- `config/local/`, which mirrors /etc/data-director/ (ADR-0026) and which git ignores: `app.env`
  (whom runs act for), `agents.env` (shared by every agent), `agents/<name>.env` (one agent's own
  settings) and `credentials/` (model keys, named by `*_FILE`). A key goes only in the file of the
  agent that uses it, never in a file every agent reads. `start` and Docker Compose read it.
- `app/config/profile.yaml`: the local copy of the profile, if the model-backed orchestrator is to
  hold the conversation.

This is a development convenience. The app and the harness stay as strict as they are: only this
script falls back to the example principal when none is set, and it says so. `start` reads the
agents and their ports from `app/config/agents.yaml`; agent `<name>` is served by `dd-<name>`.
POSIX only; on Windows, use WSL.

Each command is a module of `scripts/devstack/`; this file only reads the command line.
"""

from __future__ import annotations

import argparse
import sys

from devstack.common import DevError
from devstack.doctor import doctor
from devstack.setup import Prompter, setup
from devstack.start import start


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    setup_cmd = commands.add_parser(
        "setup", help="ask for your settings, write them, install and build"
    )
    setup_cmd.add_argument("--yes", action="store_true", help="accept every default without asking")
    setup_cmd.add_argument("--no-install", action="store_true", help="write the settings only")
    start_cmd = commands.add_parser(
        "start", help="run the agents, the app and the shell's dev server"
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
    commands.add_parser("doctor", help="check the toolchain, settings and ports; change nothing")
    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            return setup(Prompter(accept_defaults=args.yes), install=not args.no_install)
        if args.command == "start":
            return start(
                agents_only=args.agents_only, web=not args.no_web, reload=not args.no_reload
            )
        return doctor()
    except DevError as exc:
        print(f"dev.py: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt, EOFError:
        print()
        return 130


if __name__ == "__main__":
    sys.exit(main())

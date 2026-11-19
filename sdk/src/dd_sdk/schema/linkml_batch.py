"""Run several LinkML generator commands in one process (`dd_sdk.schema.gen`).

Most of a generator run is importing LinkML, so `gen` runs every command one source needs in a
single process of this module rather than one process per command. Each command is the
generator's own command line, run through its click entry point, so what it writes is exactly
what `python -m <module> <args>` writes.

Reads a JSON list of commands, each `[module, *args]`, on standard input, and writes a JSON list
of what each command printed, in the same order, on standard output.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import sys


def run(module: str, *args: str) -> str:
    """What `python -m module *args` prints."""
    command = importlib.import_module(module).cli
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        command.main(list(args), prog_name=module, standalone_mode=False)
    return printed.getvalue()


def main() -> int:
    commands: list[list[str]] = json.load(sys.stdin)
    json.dump([run(*command) for command in commands], sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

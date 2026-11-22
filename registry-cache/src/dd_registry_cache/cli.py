"""`dd-registry-cache`: what an operator does to a cache file, such as clearing it after a registry
corrects a record."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from dd_registry_cache.store import Store


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dd-registry-cache", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    clear = commands.add_parser("clear", help="remove cached answers, all or under a key prefix")
    clear.add_argument("path", type=Path, help="the cache file")
    clear.add_argument("--prefix", default="", help="only keys that start with this")
    args = parser.parse_args(argv)
    if not args.path.is_file():
        sys.stderr.write(f"no cache at {args.path}\n")
        return 1
    removed = Store(args.path).clear(args.prefix)
    sys.stdout.write(f"removed {removed} cached answers from {args.path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

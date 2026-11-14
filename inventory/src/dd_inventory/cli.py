"""`dd-inventory ROOT [ROOT ...] [--as NAME ...] [-o FILE]`: write the inventory of a dataset's
files as JSON.

Run it where the data live. It reads every file under each ROOT and sends nothing anywhere; the
researcher adds the JSON it writes to their project. Given several folders, it makes one inventory
with a part for each, listing each folder's files under its name (its own, or one given with
`--as`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dd_inventory.scan import make_inventory, make_inventory_of, tool_version

EXIT_OK, EXIT_USAGE = 0, 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dd-inventory",
        description=(
            "Describe the files under ROOT (paths, sizes, SHA-256 digests, PRONOM formats and "
            "table fields) as a Data Director FileInventory. No file content is written."
        ),
    )
    parser.add_argument(
        "roots",
        type=Path,
        nargs="+",
        metavar="ROOT",
        help="the dataset's root folder, or each of its folders",
    )
    parser.add_argument(
        "--as",
        dest="names",
        action="append",
        metavar="NAME",
        help=(
            "the name to list a folder's files under, once for each ROOT in order; by default "
            "each folder's own name, when there is more than one ROOT"
        ),
    )
    parser.add_argument(
        "-o", "--output", type=Path, help="write the inventory to this file, not standard output"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {tool_version()}")
    args = parser.parse_args(argv)

    def usage(problem: str) -> int:
        parser.print_usage(sys.stderr)
        sys.stderr.write(f"dd-inventory: {problem}\n")
        return EXIT_USAGE

    for root in args.roots:
        if not root.is_dir():
            return usage(f"{root} is not a folder")
    if args.names is not None and len(args.names) != len(args.roots):
        return usage("give --as once for each folder, or not at all")
    if len(args.roots) == 1 and args.names is None:
        inventory = make_inventory(args.roots[0])
    else:
        names = args.names or [root.resolve().name for root in args.roots]
        if len(set(names)) != len(names):
            return usage("two folders have the same name: give each a name with --as")
        try:
            inventory = make_inventory_of(dict(zip(names, args.roots, strict=True)))
        except ValueError as exc:
            return usage(f"{exc}; give each folder a name with --as")
    text = json.dumps(inventory, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

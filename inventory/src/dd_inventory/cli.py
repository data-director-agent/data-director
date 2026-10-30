"""`dd-inventory ROOT [-o FILE]`: write the inventory of a dataset's files as JSON.

Run it where the data live. It reads every file under ROOT and sends nothing anywhere; the
researcher adds the JSON it writes to their project.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dd_inventory.scan import make_inventory, tool_version

EXIT_OK, EXIT_USAGE = 0, 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dd-inventory",
        description=(
            "Describe the files under ROOT (paths, sizes, SHA-256 digests, PRONOM formats and "
            "table fields) as a Data Director FileInventory. No file content is written."
        ),
    )
    parser.add_argument("root", type=Path, metavar="ROOT", help="the dataset's root folder")
    parser.add_argument(
        "-o", "--output", type=Path, help="write the inventory to this file, not standard output"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {tool_version()}")
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        parser.print_usage(sys.stderr)
        sys.stderr.write(f"dd-inventory: {args.root} is not a folder\n")
        return EXIT_USAGE
    text = json.dumps(make_inventory(args.root), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

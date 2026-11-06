# /// script
# requires-python = ">=3.14"
# ///
"""Keep both `sources.yaml` files pinned to the repository advisor's re3data export.

The repository advisor pins one monthly re3data export in
`agents/advisor-repository/data/re3data/manifest.json` (`dd-re3data fetch --update-pin`). The
harness checks re3data evidence against the registry built from it, so each `sources.yaml`
lists that registry under the export's label with the same SHA-256. This script rewrites the
re3data entry of both files from the manifest, leaving the rest of each file as it is.

    uv run scripts/pin_re3data.py           # rewrite both entries
    uv run scripts/pin_re3data.py --check   # exit 1 if either disagrees with the manifest

An agent may read no path outside itself (docs/specs/system.md), so this lives at the root.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "agents" / "advisor-repository" / "data" / "re3data" / "manifest.json"
SOURCES = (ROOT / "app" / "config" / "sources.yaml", ROOT / "workbench" / "sources.yaml")

# The re3data entry: its snapshot_refs line, path, any comment or build lines, id_field, sha256.
ENTRY = re.compile(
    r'^(?P<indent>\s*)- snapshot_refs: \["re3data:[^\n]*\n'
    r"(?P=indent)  path: (?P<path>[^\n]*)\n"
    r"(?P<between>(?:(?P=indent)  (?:#|build:)[^\n]*\n)*)"
    r"(?P=indent)  id_field: re3data_id\n"
    r"(?P=indent)  sha256: [0-9a-f]{64}\n",
    re.MULTILINE,
)


def entry(text: str, label: str, sha256: str) -> str:
    """`text` with its re3data entry pinned to `label` and `sha256`."""
    found = list(ENTRY.finditer(text))
    if len(found) != 1:
        raise ValueError(f"expected one re3data entry, found {len(found)}")
    m = found[0]
    indent, path = m["indent"], m["path"]
    # The registry is built where the export's records used to be committed.
    path = re.sub(r"data/re3data/[^/\s]+$", "data/re3data/registry.jsonl", path)
    new = (
        f'{indent}- snapshot_refs: ["{label}"]\n'
        f"{indent}  path: {path}\n"
        f"{m['between']}"
        f"{indent}  id_field: re3data_id\n"
        f"{indent}  sha256: {sha256}\n"
    )
    return text[: m.start()] + new + text[m.end() :]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="change nothing; report drift")
    args = parser.parse_args(argv)
    pin = json.loads(MANIFEST.read_text(encoding="utf-8"))
    label, sha256 = f"re3data:export:{pin['month']}", pin["snapshot_sha256"]
    stale = []
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        try:
            pinned = entry(text, label, sha256)
        except ValueError as exc:
            sys.stderr.write(f"{path.relative_to(ROOT)}: {exc}\n")
            return 1
        if pinned != text:
            stale.append(path)
            if not args.check:
                path.write_text(pinned, encoding="utf-8")
    for path in stale:
        verb = "is not pinned to" if args.check else "pinned to"
        sys.stdout.write(f"{path.relative_to(ROOT)} {verb} {label}\n")
    return 1 if stale and args.check else 0


if __name__ == "__main__":
    raise SystemExit(main())

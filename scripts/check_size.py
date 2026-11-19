"""Check that no source file grows past the size a reviewer can hold in mind.

A module that keeps growing is usually taking on a second job. This check holds each source file
to a line limit, and each file already over it to the size recorded in `scripts/size_baseline.toml`:

- a file over the limit that has no entry in the baseline is reported;
- a file that has grown past its entry is reported;
- an entry larger than its file, or for a file now under the limit or gone, is reported, so the
  baseline only shrinks. `--update` lowers such entries and removes stale ones; it never raises
  one or adds a file.

To get a file under its entry, split it by responsibility (docs/architecture-review.md); do not
raise the entry by hand.

    uv run --no-project --python 3.14 scripts/check_size.py [--update]

It reads the files git tracks, from the repository root. It prints one problem per line and exits
1 if there is any.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "scripts" / "size_baseline.toml"

# Line limits by suffix. Physical lines, as `wc -l` counts them, so the figure needs no tool.
LIMITS = {".py": 500, ".ts": 400, ".tsx": 400}

# Where the limits apply: the packages' sources, the browser libraries and the repository tooling.
INCLUDED = ("*/src/**", "agents/*/src/**", "*/browser/src/**", "app/web/src/**", "scripts/**")

# Tests, generated code and recorded data are not designed by hand, so are not held to a size.
EXCLUDED_DIRS = {"tests", "browser_tests", "e2e", "generated", "fixtures", "node_modules"}
EXCLUDED_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".d.ts")

HEADER = """\
# Source files over the size limit in scripts/check_size.py, at the size each has reached.
#
# Written by `scripts/check_size.py --update`, which only lowers an entry or removes one. An entry
# may not grow: split the file by responsibility instead (docs/architecture-review.md). Do not add
# a file to this list to make a new one pass.
"""


@dataclass(frozen=True)
class Size:
    path: str
    lines: int
    limit: int


def in_scope(path: str) -> bool:
    pure = PurePosixPath(path)
    if pure.suffix not in LIMITS or path.endswith(EXCLUDED_SUFFIXES):
        return False
    if any(part in EXCLUDED_DIRS for part in pure.parts):
        return False
    return any(pure.full_match(pattern) for pattern in INCLUDED)


def tracked(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True, text=True
    )
    return sorted(path for path in out.stdout.split("\0") if path and in_scope(path))


def count_lines(path: Path) -> int:
    with path.open("rb") as file:
        return sum(1 for _ in file)


def oversize(root: Path) -> dict[str, Size]:
    """Each tracked source file over its limit, by path."""
    found: dict[str, Size] = {}
    for relative in tracked(root):
        file = root / relative
        if not file.is_file():
            continue  # Deleted in the working tree.
        limit = LIMITS[PurePosixPath(relative).suffix]
        lines = count_lines(file)
        if lines > limit:
            found[relative] = Size(relative, lines, limit)
    return found


def load_baseline(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    entries = tomllib.loads(path.read_text(encoding="utf-8")).get("file", [])
    return {entry["path"]: int(entry["lines"]) for entry in entries}


def write_baseline(path: Path, baseline: dict[str, int]) -> None:
    body = "".join(
        f'\n[[file]]\npath = "{name}"\nlines = {lines}\n'
        for name, lines in sorted(baseline.items())
    )
    path.write_text(HEADER + body, encoding="utf-8")


def problems(found: dict[str, Size], baseline: dict[str, int]) -> list[str]:
    report: list[str] = []
    for name, size in sorted(found.items()):
        recorded = baseline.get(name)
        if recorded is None:
            report.append(
                f"{name}: {size.lines} lines, over the limit of {size.limit}; "
                "split it by responsibility"
            )
        elif size.lines > recorded:
            report.append(
                f"{name}: grew from {recorded} to {size.lines} lines; "
                "split it rather than raise its entry"
            )
        elif size.lines < recorded:
            report.append(
                f"{name}: down to {size.lines} lines from {recorded}; lower its entry with --update"
            )
    report += [
        f"{name}: now under the limit or gone; remove its entry with --update"
        for name in sorted(baseline.keys() - found.keys())
    ]
    return report


def updated(found: dict[str, Size], baseline: dict[str, int]) -> dict[str, int]:
    """The baseline with each entry lowered to its file's size and stale entries removed."""
    return {
        name: min(recorded, found[name].lines)
        for name, recorded in baseline.items()
        if name in found
    }


def main(argv: list[str] | None = None, root: Path = ROOT, baseline_path: Path = BASELINE) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--update", action="store_true", help="lower entries and remove stale ones, then check"
    )
    args = parser.parse_args(argv)
    found = oversize(root)
    baseline = load_baseline(baseline_path)
    if args.update:
        lowered = updated(found, baseline)
        if lowered != baseline:
            write_baseline(baseline_path, lowered)
            baseline = lowered
    report = problems(found, baseline)
    for line in report:
        print(line)
    if report:
        print(f"{len(report)} size problem(s); see docs/architecture-review.md", file=sys.stderr)
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())

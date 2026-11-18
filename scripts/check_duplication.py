"""Check that no code is copied between, or within, the workspace members' sources.

Agents may not import one another, so copying a block from one agent to the next is the easy route,
and a fix to a copy is then made in one place and missed in the others (docs/architecture-review.md,
"Copying between agents"). This check runs jscpd, the copy-paste detector, over the Python and
TypeScript sources of every member and holds each pair of files to the duplication recorded in
`scripts/duplication_baseline.toml`:

- a pair of files that shares a block and has no entry in the baseline is reported;
- a pair that shares more blocks or more lines than its entry is reported;
- an entry larger than its pair's duplication, or for a pair that no longer shares a block, is
  reported, so the baseline only shrinks. `--update` lowers such entries and removes stale ones; it
  never raises one or adds a pair.

To get rid of a reported copy, move the code to the package whose job it is (`dd_sdk` for what
agents share, CONTRIBUTING.md) and import it; do not add or raise an entry by hand.

    uv run --no-project --python 3.14 scripts/check_duplication.py [--update]

It reads the files git tracks, from the repository root. jscpd is pinned in
`scripts/jscpd/package-lock.json`; the check installs it there with `npm ci` the first time, so it
needs Node.js. It prints one problem per line and exits 1 if there is any, or 2 if jscpd cannot run.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "scripts" / "duplication_baseline.toml"
TOOLING = ROOT / "scripts" / "jscpd"

# The members' sources: each package's src/, each agent's, and the browser libraries and app shell.
INCLUDED = ("*/src/**", "agents/*/src/**", "*/browser/src/**", "app/web/src/**")
SUFFIXES = {".py", ".ts", ".tsx"}

# Tests, generated code and recorded data are not designed by hand, so may repeat themselves.
EXCLUDED_DIRS = {"tests", "browser_tests", "e2e", "generated", "fixtures", "node_modules"}
EXCLUDED_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".d.ts")

# jscpd's defaults, stated so that an upgrade cannot change what counts as a copy unnoticed: a
# block of at least 5 lines and 50 tokens, compared with comments and whitespace left out ("mild").
# A .ts block copied into a .tsx file, or the other way round, counts too.
JSCPD_OPTIONS = (
    "--min-lines=5",
    "--min-tokens=50",
    "--mode=mild",
    "--format=python,typescript,tsx",
    "--cross-formats=typescript,tsx",
)

HEADER = """\
# Pairs of source files that share copied blocks, as scripts/check_duplication.py finds them, at
# the duplication each pair has reached: the number of blocks and the lines they cover.
#
# Written by `scripts/check_duplication.py --update`, which only lowers an entry or removes one. An
# entry may not grow: move the shared code to its own home instead (docs/architecture-review.md).
# Do not add a pair to this list to make a new copy pass.
"""


class JscpdUnavailableError(Exception):
    """jscpd is not installed and cannot be installed here."""


@dataclass
class Shared:
    """What two files (or one file with itself) have in common."""

    clones: int = 0
    lines: int = 0
    places: list[str] = field(default_factory=list)


Pair = tuple[str, str]


def in_scope(path: str) -> bool:
    pure = PurePosixPath(path)
    if pure.suffix not in SUFFIXES or path.endswith(EXCLUDED_SUFFIXES):
        return False
    if any(part in EXCLUDED_DIRS for part in pure.parts):
        return False
    return any(pure.full_match(pattern) for pattern in INCLUDED)


def tracked(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True, text=True
    )
    return sorted(
        path
        for path in out.stdout.split("\0")
        if path and in_scope(path) and (root / path).is_file()
    )


def _pinned_version() -> str:
    manifest = json.loads((TOOLING / "package.json").read_text(encoding="utf-8"))
    return str(manifest["devDependencies"]["jscpd"])


def _installed_version() -> str | None:
    manifest = TOOLING / "node_modules" / "jscpd" / "package.json"
    if not manifest.is_file():
        return None
    return str(json.loads(manifest.read_text(encoding="utf-8"))["version"])


def jscpd(*, install: bool = True) -> Path:
    """The pinned jscpd, installed from the lock file first if it is missing or out of date."""
    binary = TOOLING / "node_modules" / ".bin" / "jscpd"
    if _installed_version() == _pinned_version():
        return binary
    npm = shutil.which("npm")
    if not install or npm is None:
        raise JscpdUnavailableError(
            "jscpd is not installed: install Node.js, then run "
            "`npm ci --prefix scripts/jscpd --ignore-scripts`"
        )
    print("Installing jscpd from scripts/jscpd/package-lock.json", file=sys.stderr)
    subprocess.run(
        [npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--silent"],
        cwd=TOOLING,
        check=True,
    )
    return binary


def report(root: Path, files: list[str], binary: Path) -> list[dict[str, object]]:
    """jscpd's clones among `files`, each a JSON object from its report."""
    if not files:
        return []
    with tempfile.TemporaryDirectory() as output:
        subprocess.run(
            [
                str(binary),
                *JSCPD_OPTIONS,
                "--silent",
                "--no-colors",
                "--absolute",
                "--reporters=json",
                f"--output={output}",
                *files,
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads((Path(output) / "jscpd-report.json").read_text(encoding="utf-8"))
    duplicates: list[dict[str, object]] = data.get("duplicates", [])
    return duplicates


def _relative(root: Path, name: str) -> str:
    path = Path(name)
    if path.is_absolute():
        path = path.resolve().relative_to(root.resolve())
    return path.as_posix()


def by_pair(root: Path, duplicates: Iterable[dict[str, object]]) -> dict[Pair, Shared]:
    """The clones grouped by the two files they join, each pair in sorted order."""
    found: dict[Pair, Shared] = {}
    for clone in duplicates:
        first, second = clone["firstFile"], clone["secondFile"]
        assert isinstance(first, dict) and isinstance(second, dict)
        ends = sorted(
            (_relative(root, str(end["name"])), int(end["start"]), int(end["end"]))
            for end in (first, second)
        )
        pair = (ends[0][0], ends[1][0])
        shared = found.setdefault(pair, Shared())
        shared.clones += 1
        shared.lines += int(str(clone["lines"]))
        shared.places.append(" and ".join(f"{name}:{start}-{end}" for name, start, end in ends))
    return found


def duplication(root: Path, *, install: bool = True) -> dict[Pair, Shared]:
    return by_pair(root, report(root, tracked(root), jscpd(install=install)))


def load_baseline(path: Path) -> dict[Pair, Shared]:
    if not path.is_file():
        return {}
    entries = tomllib.loads(path.read_text(encoding="utf-8")).get("pair", [])
    baseline: dict[Pair, Shared] = {}
    for entry in entries:
        first, second = sorted(entry["files"])
        baseline[(first, second)] = Shared(int(entry["clones"]), int(entry["lines"]))
    return baseline


def write_baseline(path: Path, baseline: dict[Pair, Shared]) -> None:
    body = "".join(
        f'\n[[pair]]\nfiles = ["{first}", "{second}"]\n'
        f"clones = {shared.clones}\nlines = {shared.lines}\n"
        for (first, second), shared in sorted(baseline.items())
    )
    path.write_text(HEADER + body, encoding="utf-8")


def _name(pair: Pair) -> str:
    return pair[0] if pair[0] == pair[1] else f"{pair[0]} and {pair[1]}"


def _amount(shared: Shared) -> str:
    return f"{shared.clones} block(s), {shared.lines} lines"


def problems(found: dict[Pair, Shared], baseline: dict[Pair, Shared]) -> list[str]:
    report: list[str] = []
    for pair, shared in sorted(found.items()):
        recorded = baseline.get(pair)
        if recorded is None:
            report.append(
                f"{_name(pair)}: copied code, {_amount(shared)} ({'; '.join(shared.places)}); "
                "move it to one place and import it"
            )
        elif shared.clones > recorded.clones or shared.lines > recorded.lines:
            report.append(
                f"{_name(pair)}: copied code grew from {_amount(recorded)} to {_amount(shared)} "
                f"({'; '.join(shared.places)}); move it to one place rather than raise its entry"
            )
        elif shared.clones < recorded.clones or shared.lines < recorded.lines:
            report.append(
                f"{_name(pair)}: down to {_amount(shared)} from {_amount(recorded)}; "
                "lower its entry with --update"
            )
    report += [
        f"{_name(pair)}: no longer share a block; remove its entry with --update"
        for pair in sorted(baseline.keys() - found.keys())
    ]
    return report


def updated(found: dict[Pair, Shared], baseline: dict[Pair, Shared]) -> dict[Pair, Shared]:
    """The baseline with each entry lowered to its pair's duplication and stale entries removed."""
    return {
        pair: Shared(
            min(recorded.clones, found[pair].clones), min(recorded.lines, found[pair].lines)
        )
        for pair, recorded in baseline.items()
        if pair in found
    }


def _same(left: dict[Pair, Shared], right: dict[Pair, Shared]) -> bool:
    def key(table: dict[Pair, Shared]) -> dict[Pair, tuple[int, int]]:
        return {pair: (shared.clones, shared.lines) for pair, shared in table.items()}

    return key(left) == key(right)


def main(
    argv: list[str] | None = None,
    root: Path = ROOT,
    baseline_path: Path = BASELINE,
    *,
    install: bool = True,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--update", action="store_true", help="lower entries and remove stale ones, then check"
    )
    args = parser.parse_args(argv)
    try:
        found = duplication(root, install=install)
    except (JscpdUnavailableError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", None) or ""
        print(f"cannot run jscpd: {error} {detail}".strip(), file=sys.stderr)
        return 2
    baseline = load_baseline(baseline_path)
    if args.update:
        lowered = updated(found, baseline)
        if not _same(lowered, baseline):
            write_baseline(baseline_path, lowered)
            baseline = lowered
    report = problems(found, baseline)
    for line in report:
        print(line)
    if report:
        print(
            f"{len(report)} duplication problem(s); see docs/architecture-review.md",
            file=sys.stderr,
        )
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())

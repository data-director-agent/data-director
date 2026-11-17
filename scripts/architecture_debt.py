"""Count the architecture debt the repository records, for the CI job summary.

The size and complexity checks are ratchets (docs/architecture-review.md): the code that was over a
limit when a check arrived carries a marker, and each marker should go when its code is split. This
script counts what is recorded, so that the count can be seen to fall:

- Ruff complexity markers, a `noqa` naming `C901` or a `PLR09…` code, in Python outside tests;
- ESLint complexity markers, `eslint-disable-next-line complexity`, in TypeScript and JavaScript
  outside tests;
- the entries in `scripts/size_baseline.toml`;
- the exceptions in `scripts/boundaries.toml`;
- the `ignore_imports` of the Import Linter contracts in the root `pyproject.toml`.

    uv run --no-project --python 3.14 scripts/architecture_debt.py [--summary PATH]

It reads the files git tracks, from the repository root, and prints a Markdown table; with
`--summary` it appends the table to that file as well (CI passes `$GITHUB_STEP_SUMMARY`). It is
information only: it always exits 0.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]

# A marker suppresses a function's complexity. One per marked line, however many codes it names.
RUFF_MARKER = re.compile(r"#\s*noqa:[^#\n]*\b(?:C901|PLR09\d\d)\b")
# A directive opens its comment; a comment that only mentions one is not a marker.
ESLINT_MARKER = re.compile(r"(?://|/\*)\s*eslint-disable-next-line\s+complexity\b")

PYTHON = {".py"}
SCRIPT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}

# The lint rules do not apply to tests, and tests of this script plant markers on purpose.
EXCLUDED_DIRS = {"tests", "browser_tests", "e2e", "node_modules"}
EXCLUDED_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")


@dataclass(frozen=True)
class Count:
    what: str
    where: str
    number: int


def in_scope(path: str) -> bool:
    pure = PurePosixPath(path)
    if any(part in EXCLUDED_DIRS for part in pure.parts):
        return False
    return not path.endswith(EXCLUDED_SUFFIXES)


def tracked(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True, text=True
    )
    return sorted(path for path in out.stdout.split("\0") if path and in_scope(path))


def markers(root: Path, files: list[str], suffixes: set[str], pattern: re.Pattern[str]) -> int:
    total = 0
    for relative in files:
        file = root / relative
        if PurePosixPath(relative).suffix not in suffixes or not file.is_file():
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        total += sum(1 for line in text.splitlines() if pattern.search(line))
    return total


def toml(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def entries(path: Path, key: str) -> int:
    found = toml(path).get(key, [])
    return len(found) if isinstance(found, list) else 0


def ignored_imports(pyproject: Path) -> int:
    tool = toml(pyproject).get("tool", {})
    linter = tool.get("importlinter", {}) if isinstance(tool, dict) else {}
    contracts = linter.get("contracts", []) if isinstance(linter, dict) else []
    return sum(
        len(contract.get("ignore_imports", []))
        for contract in contracts
        if isinstance(contract, dict)
    )


def counts(root: Path) -> list[Count]:
    files = tracked(root)
    return [
        Count(
            "Ruff complexity markers",
            "`# noqa: C901`, `PLR09…`",
            markers(root, files, PYTHON, RUFF_MARKER),
        ),
        Count(
            "ESLint complexity markers",
            "`eslint-disable-next-line complexity`",
            markers(root, files, SCRIPT, ESLINT_MARKER),
        ),
        Count(
            "Files over the size limit",
            "`scripts/size_baseline.toml`",
            entries(root / "scripts" / "size_baseline.toml", "file"),
        ),
        Count(
            "Boundary exceptions",
            "`scripts/boundaries.toml`",
            entries(root / "scripts" / "boundaries.toml", "exception"),
        ),
        Count(
            "Import Linter exceptions",
            "`ignore_imports` in `pyproject.toml`",
            ignored_imports(root / "pyproject.toml"),
        ),
    ]


def report(found: list[Count]) -> str:
    rows = "".join(f"| {count.what} | {count.where} | {count.number} |\n" for count in found)
    return (
        "## Recorded architecture debt\n\n"
        "Each count should only fall (`docs/architecture-review.md`).\n\n"
        "| Debt | Where | Count |\n|---|---|---:|\n"
        f"{rows}"
        f"| **Total** | | **{sum(count.number for count in found)}** |\n"
    )


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--summary", type=Path, help="append the table to this Markdown file")
    args = parser.parse_args(argv)
    try:
        table = report(counts(root))
    except (OSError, subprocess.CalledProcessError, tomllib.TOMLDecodeError) as error:
        # Information only: a failure to count never fails the run.
        print(f"architecture_debt: could not count: {error}", file=sys.stderr)
        return 0
    print(table, end="")
    if args.summary is not None:
        with args.summary.open("a", encoding="utf-8") as file:
            file.write(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())

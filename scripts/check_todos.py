"""Check that every TODO in the repository names the issue that will resolve it.

AGENTS.md asks for an explicit TODO rather than a plausible guess. So that each one has an
owner, a TODO is written with its issue reference directly after it, `TODO(#123)` or
`TODO(#41, #57)`. A bare TODO, or one whose reference is separated from it, is reported.

    uv run python scripts/check_todos.py

It reads the files git tracks, from the repository root, except those in `EXCLUDED`. It prints
one `path:line: text` per problem and exits 1 if there is any.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The Blueprint is external material reproduced verbatim (AGENTS.md); release-please writes each
# CHANGELOG.md from commit subjects, which may mention the word; this script must name it.
EXCLUDED_PATHS = ("docs/BLUEPRINT.md", "scripts/check_todos.py")
EXCLUDED_NAMES = ("CHANGELOG.md",)
EXCLUDED_DIRS = ("node_modules",)

WORD = re.compile(r"\bTODO\b")
REFERENCED = re.compile(r"TODO\(#\d+(?:, #\d+)*\)")


def unreferenced(line: str) -> bool:
    """Whether `line` holds a TODO without an issue reference."""
    return len(WORD.findall(line)) > len(REFERENCED.findall(line))


def excluded(path: str) -> bool:
    parts = path.split("/")
    return (
        path in EXCLUDED_PATHS
        or parts[-1] in EXCLUDED_NAMES
        or any(part in EXCLUDED_DIRS for part in parts)
    )


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True, text=True
    )
    return [path for path in out.stdout.split("\0") if path and not excluded(path)]


def file_problems(path: str) -> list[str]:
    """`path:line: text` for each unreferenced TODO in the file at `path`."""
    try:
        text = (ROOT / path).read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        # A binary file, or one deleted or replaced by a directory in the working tree.
        return []
    return [
        f"{path}:{number}: {line.strip()}"
        for number, line in enumerate(text.splitlines(), start=1)
        if unreferenced(line)
    ]


def main() -> int:
    problems = [problem for path in tracked_files() for problem in file_problems(path)]
    for problem in problems:
        print(problem)
    if problems:
        print(
            f"{len(problems)} TODO(s) without an issue reference; write TODO(#123) (AGENTS.md)",
            file=sys.stderr,
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

"""Check that no two decision records in docs/adr/ share a number.

Records are named `NNNN-slug.md`, and a record is cited by its number (`ADR-0016`), so two
files with one number make a citation ambiguous. Parallel branches each take "the next number"
and collide when both merge; this reports it.

    uv run python scripts/check_adr_numbers.py

It reads the file names in `docs/adr/` and prints one line per shared number. It exits 1 if
any number is shared other than those in `LEGACY_SHARED`.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ADR_DIR = Path(__file__).resolve().parents[1] / "docs" / "adr"

# Two records share 0016 from before numbers were required to be unique (docs/adr/README.md,
# Numbering); they are cited by file name. No other number may be added here.
LEGACY_SHARED = frozenset({"0016"})

NAME = re.compile(r"^(\d{4})-.+\.md$")


def shared_numbers(names: list[str]) -> dict[str, list[str]]:
    """Each number held by more than one of `names`, with its file names, less the legacy ones."""
    by_number: dict[str, list[str]] = defaultdict(list)
    for name in sorted(names):
        match = NAME.match(name)
        if match:
            by_number[match.group(1)].append(name)
    return {
        number: files
        for number, files in by_number.items()
        if len(files) > 1 and number not in LEGACY_SHARED
    }


def main() -> int:
    shared = shared_numbers([path.name for path in ADR_DIR.glob("*.md")])
    for number, files in sorted(shared.items()):
        print(f"ADR-{number} is shared by {', '.join(files)}")
    if shared:
        print("Each decision record needs its own number (docs/adr/README.md)", file=sys.stderr)
    return 1 if shared else 0


if __name__ == "__main__":
    sys.exit(main())

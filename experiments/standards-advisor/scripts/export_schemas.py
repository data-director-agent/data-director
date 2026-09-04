#!/usr/bin/env python3
"""Regenerate `schemas/*.json` from the Pydantic models.

    uv run python scripts/export_schemas.py

The logic lives in `standards_advisor.schema_export` so that the CLI's `export-schemas`
subcommand and the drift test use exactly the same code path as this script.
"""

from __future__ import annotations

import sys
from pathlib import Path

from standards_advisor.schema_export import write_schemas
from standards_advisor.settings import find_project_root


def main() -> int:
    root = find_project_root(Path(__file__))
    changed = write_schemas(root / "schemas")
    if not changed:
        print("schemas are already current")
        return 0
    for path in changed:
        print(f"wrote {path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

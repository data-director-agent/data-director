"""Check that each workspace member declares the third-party packages it imports.

Runs `deptry` once per member, inside the workspace environment that holds the member's
dependencies (a member's own directory is the project root, so its own `[project]` and
`[dependency-groups]` are what is compared with its imports). It reports:

- DEP001: an import that matches no installed package;
- DEP002: a declared dependency that the member never imports;
- DEP003: an import of a package the member does not declare, which is installed only because
  something else needs it (a transitive dependency);
- DEP004: a development dependency imported from `src/`.

`scripts/check_boundaries.py` and `lint-imports` cover the workspace members themselves; this
covers everything else. deptry cannot tell which import name an editable install provides, so
this script gives it each member's name and modules. Any other package whose import name differs
from its distribution name goes in `IMPORT_NAMES`, per package; none is ignored wholesale.

    uv sync --all-packages --all-extras
    uv run python scripts/check_dependencies.py [member ...]

Exits 1 if deptry reports a problem for any member.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Distribution name to import name, for third-party packages deptry cannot work out itself.
IMPORT_NAMES: dict[str, str] = {}


def members() -> list[Path]:
    """The workspace members, from the root `[tool.uv.workspace]`."""
    workspace = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["uv"]["workspace"]
    found: list[Path] = []
    for pattern in workspace["members"]:
        found.extend(
            path for path in sorted(ROOT.glob(pattern)) if (path / "pyproject.toml").is_file()
        )
    return found


def modules(member: Path) -> list[str]:
    """The top-level packages the member ships, which deptry must treat as its own code."""
    source = member / "src"
    if not source.is_dir():
        return []
    return sorted(
        path.name
        for path in source.iterdir()
        if path.is_dir() and path.name != "__pycache__" and not path.name.endswith(".egg-info")
    )


def import_names(everyone: list[Path]) -> str:
    """The `--package-module-name-map` value: each member's distribution and its modules."""
    mapping = dict(IMPORT_NAMES)
    for member in everyone:
        name = tomllib.loads((member / "pyproject.toml").read_text())["project"]["name"]
        mapping[name] = "|".join(modules(member))
    return ",".join(f"{name}={module}" for name, module in mapping.items())


def check(member: Path, mapping: str) -> bool:
    """Run deptry for one member; True when it reports nothing."""
    command = [
        "deptry",
        ".",
        "--known-first-party",
        ",".join(modules(member)),
        "--package-module-name-map",
        mapping,
    ]
    result = subprocess.run(command, cwd=member, check=False)
    return result.returncode == 0


def main(argv: list[str]) -> int:
    wanted = {Path(arg).resolve() for arg in argv}
    everyone = members()
    mapping = import_names(everyone)
    chosen = [m for m in everyone if not wanted or m in wanted]
    if wanted and len(chosen) != len(wanted):
        print(
            "error: not a workspace member:",
            *sorted(map(str, wanted - set(chosen))),
            file=sys.stderr,
        )
        return 2
    failed = []
    for member in chosen:
        print(f"== {member.relative_to(ROOT)}", flush=True)
        if not check(member, mapping):
            failed.append(member.relative_to(ROOT))
    if failed:
        print("\ndeptry found problems in:", *map(str, failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

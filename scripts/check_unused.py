"""Check that the workspace members' sources hold no code that nothing calls.

Refactors leave behind functions, methods, classes and imports that nothing reaches any more.
This check runs vulture (https://github.com/jendrikseipp/vulture) over every Python file git
tracks, so that a use in a test or a script counts, and reports what it finds unused in a
member's `src/`. Each finding must be removed or have an entry in `scripts/unused_code.toml`:

- `[[reached]]`: code reached at run time by a name vulture cannot see (a template, a base class
  or library that calls it, a `getattr`), with `how` it is reached;
- `[[unused]]`: unused code recorded when this check was added, which may only shrink.

An entry that no longer matches a finding is reported, so neither list keeps a stale entry.
`--update` removes stale entries; it never adds one. Unused variables are not checked: vulture
reports every Pydantic field and enum member as one, and Ruff already finds unused locals.

    uv run python scripts/check_unused.py [--update]

It runs from the repository root, prints one problem per line and exits 1 if there is any.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import vulture

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = ROOT / "scripts" / "unused_code.toml"

# vulture's own threshold for code that might be reached dynamically; anything above is certain.
MIN_CONFIDENCE = 60

# Where a finding counts: the members' sources.
CHECKED = ("*/src/**", "agents/*/src/**")

# Generated code is not written by hand, so is neither checked nor read.
EXCLUDED_DIRS = {"generated"}

# Pydantic calls validators itself: a method so decorated is reached, whatever its name.
IGNORE_DECORATORS = ["@model_validator", "@field_validator"]

# Pydantic fields, enum members and module constants: see the docstring.
UNCHECKED_KINDS = {"variable"}

HEADER = """\
# Code in the workspace members' sources that vulture finds unused, checked by
# scripts/check_unused.py. An entry no finding matches fails the check: remove it, or run
# `scripts/check_unused.py --update`.
#
# [[reached]]: reached at run time by a name vulture cannot see; `how` says what reaches it. Add
#   an entry only for code that is used.
# [[unused]]: unused code recorded when the check was added (#1058). It only shrinks: delete the
#   code, or call it, and remove its entry. Never add one; delete the code instead.
"""


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    name: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.path, self.name)


@dataclass(frozen=True)
class Allowed:
    reached: dict[tuple[str, str], str]  # (path, name) -> how it is reached
    unused: set[tuple[str, str]]


def tracked(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
    )
    return sorted(
        path
        for path in out.stdout.split("\0")
        if path
        and not EXCLUDED_DIRS.intersection(PurePosixPath(path).parts)
        and (root / path).is_file()
    )


def checked(path: str) -> bool:
    pure = PurePosixPath(path)
    return any(pure.full_match(pattern) for pattern in CHECKED)


def findings(root: Path) -> list[Finding]:
    """What vulture finds unused in the members' sources, reading every tracked file."""
    scanner = vulture.Vulture(ignore_decorators=IGNORE_DECORATORS)
    scanner.scavenge([str(root / path) for path in tracked(root)])
    found: list[Finding] = []
    for item in scanner.get_unused_code(min_confidence=MIN_CONFIDENCE):
        path = Path(item.filename).resolve().relative_to(root.resolve()).as_posix()
        if item.typ in UNCHECKED_KINDS or not checked(path):
            continue
        found.append(Finding(path, item.first_lineno, item.typ, item.name))
    return sorted(found, key=lambda f: (f.path, f.line, f.name))


def load_allowed(path: Path) -> Allowed:
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return Allowed(
        reached={(e["path"], e["name"]): e["how"] for e in data.get("reached", [])},
        unused={(e["path"], e["name"]) for e in data.get("unused", [])},
    )


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_allowed(path: Path, allowed: Allowed) -> None:
    reached = "".join(
        f"\n[[reached]]\npath = {_quote(p)}\nname = {_quote(n)}\nhow = {_quote(how)}\n"
        for (p, n), how in sorted(allowed.reached.items())
    )
    unused = "".join(
        f"\n[[unused]]\npath = {_quote(p)}\nname = {_quote(n)}\n" for p, n in sorted(allowed.unused)
    )
    path.write_text(HEADER + reached + unused, encoding="utf-8")


def problems(found: list[Finding], allowed: Allowed) -> list[str]:
    report = [
        f"{f.path}:{f.line}: unused {f.kind} '{f.name}'; delete it, or record how it is reached"
        for f in found
        if f.key not in allowed.reached and f.key not in allowed.unused
    ]
    keys = {f.key for f in found}
    report += [
        f"{p}: '{n}' is listed in [[reached]] but no longer found unused; remove its entry"
        for p, n in sorted(allowed.reached.keys() - keys)
    ]
    report += [
        f"{p}: '{n}' is listed in [[unused]] but no longer found unused; remove its entry"
        for p, n in sorted(allowed.unused - keys)
    ]
    return report


def updated(found: list[Finding], allowed: Allowed) -> Allowed:
    """The allow-lists without the entries that no finding matches."""
    keys = {f.key for f in found}
    return Allowed(
        reached={k: how for k, how in allowed.reached.items() if k in keys},
        unused={k for k in allowed.unused if k in keys},
    )


def main(argv: list[str] | None = None, root: Path = ROOT, allowed_path: Path = ALLOWED) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--update", action="store_true", help="remove stale entries, then check")
    args = parser.parse_args(argv)
    found = findings(root)
    allowed = load_allowed(allowed_path)
    if args.update:
        pruned = updated(found, allowed)
        if pruned != allowed:
            write_allowed(allowed_path, pruned)
            allowed = pruned
    report = problems(found, allowed)
    for line in report:
        print(line)
    if report:
        print(
            f"{len(report)} unused-code problem(s); see scripts/unused_code.toml", file=sys.stderr
        )
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())

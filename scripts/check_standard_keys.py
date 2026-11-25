"""Check that no module outside a metadata standard's definition names one of its properties
(docs/specs/metadata-standards.md, invariant 3).

A standard is a definition, not code: what a property is called, where it is written and which
pivot term it means is said once, in the standard's definition under `metadata-records/`. A module
that names a property's key instead reads one standard only, and a record in any other would pass
it by unread. So every string literal in a member's `src/` that is one of a definition's
distinctive identifiers is reported: a property's path or a key of it, a value key, a part key or a
qualifier key, where it is written in camelCase or as a dotted path, as `rightsList` or
`types.resourceTypeGeneral` are. Plain words such as `titles` are left out, since they name other
things too. Docstrings are not read.

    uv run python scripts/check_standard_keys.py

The exceptions in `EXEMPT` only shrink: each names the issue that removes it, and one that no
longer names anything fails. It prints one `path:line: text` per problem and exits 1 if there is
any.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFINITIONS = ROOT / "metadata-records" / "src" / "dd_metadata_records" / "standards"
# The members whose src/ is read: every member but the library that holds the definitions.
MEMBERS = ("sdk", "harness", "workbench", "app", "admin", "agents")
# Members that still name a standard's properties, each with the issue that removes it.
EXEMPT: dict[str, str] = {}
DISTINCTIVE = re.compile(r"[a-z][a-z0-9]*[A-Z][A-Za-z0-9]*|[A-Za-z]+(\.[A-Za-z]+)+")


def identifiers(definition: Mapping[str, Any]) -> set[str]:
    """The distinctive identifiers one definition names: its properties' paths and their keys,
    and the value, part and qualifier keys of each."""
    found: set[str] = set()
    for path, spec in (definition.get("properties") or {}).items():
        found |= {path, *path.split(".")}
        found |= set(_keys(spec))
    return {name for name in found if DISTINCTIVE.fullmatch(name)}


def _keys(spec: Any) -> Iterator[str]:
    if not isinstance(spec, dict):
        return
    if isinstance(spec.get("value"), str):
        yield spec["value"]
    for rule in spec.get("qualified") or ():
        yield from rule.get("when") or {}
    for key, part in (spec.get("parts") or {}).items():
        yield key
        yield from _keys(part)


def all_identifiers(directory: Path = DEFINITIONS) -> set[str]:
    found: set[str] = set()
    for path in sorted(directory.glob("*.yaml")):
        found |= identifiers(yaml.safe_load(path.read_text(encoding="utf-8")))
    return found


def _docstrings(tree: ast.AST) -> set[int]:
    """The ids of the string constants that are docstrings."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                found.add(id(body[0].value))
    return found


def named(source: str, names: set[str]) -> list[tuple[int, str]]:
    """The line and text of each string literal in `source` that is one of `names`."""
    tree = ast.parse(source)
    skip = _docstrings(tree)
    return sorted(
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value in names
        and id(node) not in skip
    )


def sources(root: Path = ROOT) -> Iterator[Path]:
    for member in MEMBERS:
        for path in sorted((root / member).rglob("src/**/*.py")):
            if "node_modules" not in path.parts and ".venv" not in path.parts:
                yield path


def problems(paths: Iterable[Path], names: set[str], root: Path = ROOT) -> list[str]:
    found = []
    used: set[str] = set()
    for path in paths:
        relative = path.relative_to(root).as_posix()
        exempt = next((key for key in EXEMPT if relative.startswith(key + "/")), None)
        hits = named(path.read_text(encoding="utf-8"), names)
        if exempt:
            used |= {exempt} if hits else set()
            continue
        found += [
            f"{relative}:{line}: names {text!r}, a property of a standard" for line, text in hits
        ]
    found += [
        f"{key}: exempt until {issue} but names no standard's property; remove it from EXEMPT"
        for key, issue in EXEMPT.items()
        if key not in used
    ]
    return found


def main() -> int:
    found = problems(sources(), all_identifiers())
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())

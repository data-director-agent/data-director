"""The app runs no agent in its own process (ADR-0027): it reaches every agent over A2A through
the conductor, so it imports no agent package, and never the workbench (AGENTS.md)."""

from __future__ import annotations

import ast
from pathlib import Path

import dd_app

SOURCE = Path(dd_app.__file__).resolve().parent
FORBIDDEN = ("workbench", "dd_agent_")


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _forbidden(module: str) -> bool:
    top = module.split(".")[0]
    return any(top == f or (f.endswith("_") and top.startswith(f)) for f in FORBIDDEN)


def test_the_app_imports_no_agent_and_not_the_workbench() -> None:
    found = {
        f"{path.relative_to(SOURCE)}: {module}"
        for path in SOURCE.rglob("*.py")
        for module in _imported_modules(path)
        if _forbidden(module)
    }
    assert not found


def test_the_check_sees_a_forbidden_import() -> None:
    assert _forbidden("dd_agent_advisor_standards.factory")
    assert _forbidden("workbench.testing")
    assert not _forbidden("dd_harness.conductor")

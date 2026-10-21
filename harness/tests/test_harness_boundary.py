"""The harness stands on its own (ADR-0022): it imports the SDK and third-party libraries, never
a way in to it (the workbench, the app), an agent, or the evaluation framework."""

from __future__ import annotations

import ast
from pathlib import Path

import dd_harness

SOURCE = Path(dd_harness.__file__).resolve().parent
FORBIDDEN = ("workbench", "dd_app", "dd_agent_", "inspect_ai")


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


def test_the_harness_imports_no_way_in_and_no_agent() -> None:
    found = {
        f"{path.relative_to(SOURCE)}: {module}"
        for path in SOURCE.rglob("*.py")
        for module in _imported_modules(path)
        if _forbidden(module)
    }
    assert not found


def test_the_check_sees_a_forbidden_import() -> None:
    assert _forbidden("workbench.testing")
    assert _forbidden("dd_agent_r3.agent")
    assert not _forbidden("dd_sdk.agent")

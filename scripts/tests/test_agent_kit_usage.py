"""No agent writes out what the agent kit in `dd_sdk.agent` already gives it.

`abstain`, `input_ref` and `input_evidence` live in the SDK because agents may not import one
another; a private copy in an agent is the drift they were moved there to stop
(docs/architecture-review.md, finding 4).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCES = sorted((ROOT / "agents").glob("*/src/**/*.py"))


def _cites_the_input(call: ast.Call) -> bool:
    """A `GroundingRef(...)` or `EvidenceItem(...)` whose source_id is `ctx.input_ref`."""
    name = call.func.id if isinstance(call.func, ast.Name) else None
    if name not in {"GroundingRef", "EvidenceItem"}:
        return False
    return any(
        keyword.arg == "source_id" and ast.unparse(keyword.value) == "ctx.input_ref"
        for keyword in call.keywords
    )


def _copies(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.FunctionDef) and node.name in {"_abstain", "_input_evidence"}:
            found.append(f"{node.lineno}: defines {node.name}; use dd_sdk.agent's kit")
        elif isinstance(node, ast.Call) and _cites_the_input(node):
            found.append(f"{node.lineno}: cites the input by hand; use input_ref or input_evidence")
    return found


def test_there_are_agent_sources() -> None:
    assert SOURCES


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: str(path.relative_to(ROOT)))
def test_agent_uses_the_kit(path: Path) -> None:
    assert _copies(path) == []


def test_the_check_finds_a_copy(tmp_path: Path) -> None:
    planted = tmp_path / "agent.py"
    planted.write_text(
        "def _abstain(reason, statement): ...\n"
        "ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)\n",
        encoding="utf-8",
    )
    assert len(_copies(planted)) == 2

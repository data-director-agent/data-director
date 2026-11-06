"""The rule in scripts/check_boundaries.py that each workspace member keeps to its own directory."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_boundaries as cb  # noqa: E402

AGENT = cb.Member(
    path="agents/echo",
    name="data-director-agent-echo",
    modules=frozenset({"dd_agent_echo"}),
    runtime=frozenset({"data-director-sdk", "pyyaml"}),
    dev=frozenset({"data-director-harness"}),
)
OWNERS = {
    "dd_sdk": "data-director-sdk",
    "dd_harness": "data-director-harness",
    "workbench": "data-director-workbench",
    "dd_agent_echo": "data-director-agent-echo",
}


def test_requirement_names_drop_versions_extras_and_markers() -> None:
    assert cb.requirement_names(
        [
            "data-director-sdk>=0.2.0a0",
            "data_director.Harness[serve]",
            "pyyaml ; python_version>'3'",
        ]
    ) == {"data-director-sdk", "data-director-harness", "pyyaml"}


def test_imports_are_absolute_and_top_level() -> None:
    source = "import dd_sdk.agent\nfrom dd_harness.testing import claim\nfrom . import sibling\n"
    assert cb.imports(source) == [(1, "dd_sdk"), (2, "dd_harness")]


@pytest.mark.parametrize(
    ("path", "n", "leaves"),
    [
        ("agents/echo/tests/test_echo.py", 1, False),
        ("agents/echo/tests/test_echo.py", 2, True),
        ("agents/echo/src/dd_agent_echo/agent.py", 2, False),
        ("agents/echo/src/dd_agent_echo/agent.py", 3, True),
    ],
)
def test_parents_leave_the_member_past_its_directory(path: str, n: int, leaves: bool) -> None:
    source = f"HERE = Path(__file__).resolve().parents[{n}]\n"
    assert bool(cb.climbs_out(path, "agents/echo", source)) is leaves


def test_src_may_import_only_its_dependencies() -> None:
    source = "import dd_sdk\nimport dd_harness\nimport dd_agent_echo.classes\n"
    problems = cb.file_problems("agents/echo/src/dd_agent_echo/agent.py", AGENT, OWNERS, source)
    assert [str(p) for p in problems] == [
        "agents/echo/src/dd_agent_echo/agent.py:2: "
        "imports dd_harness (data-director-harness), not in its dependencies"
    ]


def test_tests_may_also_import_the_dev_group() -> None:
    source = "import dd_harness\nimport workbench\n"
    problems = cb.file_problems("agents/echo/tests/test_echo.py", AGENT, OWNERS, source)
    assert [p.detail.split(" (")[0] for p in problems] == ["imports workbench"]


def _workspace(root: Path) -> None:
    (root / "pyproject.toml").write_text('[tool.uv.workspace]\nmembers = ["agents/*"]\n')
    echo = root / "agents" / "echo"
    (echo / "src" / "dd_agent_echo").mkdir(parents=True)
    (echo / "pyproject.toml").write_text(
        '[project]\nname = "data-director-agent-echo"\ndependencies = []\n'
    )
    (echo / "src" / "dd_agent_echo" / "agent.py").write_text(
        "from pathlib import Path\nROOT = Path(__file__).parents[4]\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)


def test_an_exception_hides_its_problem_and_a_stale_one_is_reported(tmp_path: Path) -> None:
    _workspace(tmp_path)
    agent = "agents/echo/src/dd_agent_echo/agent.py"
    assert cb.problems(tmp_path, allowed=set()) == [
        f"{agent}:2: reads outside agents/echo/ (parents[4])"
    ]
    assert cb.problems(tmp_path, allowed={(agent, "reads outside")}) == []
    stale = cb.problems(tmp_path, allowed={(agent, "reads outside"), (agent, "imports dd_sdk")})
    assert len(stale) == 1
    assert "no longer 'imports dd_sdk'" in stale[0]

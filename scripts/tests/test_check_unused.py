"""The unused-code check in scripts/check_unused.py: what nothing calls fails, and allow-lists
only hold entries that still match."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_unused as cu  # noqa: E402

MODULE = "harness/src/dd_harness/helpers.py"
CALLER = "harness/src/dd_harness/caller.py"
TEST = "harness/tests/test_helpers.py"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", relative], cwd=root, check=True)


def _check(root: Path, *argv: str) -> int:
    return cu.main(list(argv), root=root, allowed_path=root / "unused.toml")


@pytest.mark.parametrize(
    ("path", "is_checked"),
    [
        ("harness/src/dd_harness/conductor.py", True),
        ("agents/advisor-policy/src/dd_agent_advisor_policy/agent.py", True),
        ("harness/tests/test_harness.py", False),
        ("scripts/check_size.py", False),
        ("conftest.py", False),
    ],
)
def test_scope(path: str, is_checked: bool) -> None:
    assert cu.checked(path) is is_checked


def test_a_called_function_passes(repo: Path) -> None:
    _write(repo, MODULE, "def helper() -> int:\n    return 1\n")
    _write(repo, CALLER, "from dd_harness.helpers import helper\n\nprint(helper())\n")
    assert _check(repo) == 0


def test_a_use_in_a_test_counts(repo: Path) -> None:
    _write(repo, MODULE, "def helper() -> int:\n    return 1\n")
    _write(repo, TEST, "from dd_harness.helpers import helper\n\nassert helper()\n")
    assert _check(repo) == 0


def test_an_unused_function_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, MODULE, "def helper() -> int:\n    return 1\n")
    assert _check(repo) == 1
    assert "helper" in capsys.readouterr().out


def test_an_unused_method_and_import_fail(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, MODULE, "import json\n\n\nclass Used:\n    def method(self) -> None: ...\n")
    _write(repo, CALLER, "from dd_harness.helpers import Used\n\nprint(Used())\n")
    assert _check(repo) == 1
    out = capsys.readouterr().out
    assert "method" in out
    assert "json" in out


def test_a_validator_is_reached(repo: Path) -> None:
    _write(
        repo,
        MODULE,
        "from pydantic import BaseModel, model_validator\n\n\n"
        "class Model(BaseModel):\n"
        '    @model_validator(mode="after")\n'
        "    def _check(self) -> Model:\n"
        "        return self\n",
    )
    _write(repo, CALLER, "from dd_harness.helpers import Model\n\nprint(Model())\n")
    assert _check(repo) == 0


def test_generated_code_is_not_read(repo: Path) -> None:
    _write(repo, "sdk/src/dd_sdk/schema/generated/core.py", "def generated() -> None: ...\n")
    assert _check(repo) == 0


def test_an_allowed_entry_passes_and_a_stale_one_fails(repo: Path) -> None:
    allowed = repo / "unused.toml"
    _write(repo, MODULE, "def helper() -> int:\n    return 1\n")
    cu.write_allowed(allowed, cu.Allowed(reached={}, unused={(MODULE, "helper")}))
    assert _check(repo) == 0
    _write(repo, CALLER, "from dd_harness.helpers import helper\n\nprint(helper())\n")
    assert _check(repo) == 1  # The entry is stale: helper is now called.
    assert _check(repo, "--update") == 0
    assert cu.load_allowed(allowed) == cu.Allowed(reached={}, unused=set())


def test_a_stale_reached_entry_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, MODULE, "def helper() -> int:\n    return 1\n")
    _write(repo, CALLER, "from dd_harness.helpers import helper\n\nprint(helper())\n")
    entry = {(MODULE, "gone"): "a template calls it"}
    cu.write_allowed(repo / "unused.toml", cu.Allowed(reached=entry, unused=set()))
    assert _check(repo) == 1
    assert "gone" in capsys.readouterr().out


def test_update_keeps_how_an_entry_is_reached(repo: Path) -> None:
    allowed = repo / "unused.toml"
    _write(repo, MODULE, "def handle_data() -> None: ...\n")
    entry = {(MODULE, "handle_data"): 'HTMLParser calls it, "by name"'}
    cu.write_allowed(allowed, cu.Allowed(reached=entry, unused={(MODULE, "gone")}))
    assert _check(repo, "--update") == 0
    assert cu.load_allowed(allowed) == cu.Allowed(reached=entry, unused=set())


def test_the_repository_passes() -> None:
    assert cu.problems(cu.findings(ROOT), cu.load_allowed(cu.ALLOWED)) == []

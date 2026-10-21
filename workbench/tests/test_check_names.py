"""The pull request title and branch name rules in scripts/check_names.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_names as cn  # noqa: E402


@pytest.mark.parametrize(
    "title",
    [
        "feat(app): register every in-tree agent",
        "ci: pin Python 3.14, run pytest under xdist, upload coverage once",
        "ci(release-please): pin actions, scope permissions per job",
        "refactor(harness)!: rename the run store",
        "docs: cite the community consultation that preceded the Blueprint",
        "feat(docs): GitHub Pages site",
        "fix(sdk): ADR-0019 class names",
    ],
)
def test_good_titles(title: str) -> None:
    assert cn.title_problems(title) == []


@pytest.mark.parametrize(
    ("title", "fragment"),
    [
        ("Rename the R3 agent to the standards advisor", "Conventional Commits"),
        ("feature(app): history tab", "type 'feature'"),
        ("feat(App): history tab", "scope 'App'"),
        ("feat(): history tab", "scope ''"),
        ("feat: Add a history tab", "capital"),
        ("feat: a history tab.", "full stop"),
        ("feat: ", "empty"),
        ("feat:history tab", "Conventional Commits"),
        ("feat: " + "x" * cn.MAX_TITLE, "limit"),
    ],
)
def test_bad_titles(title: str, fragment: str) -> None:
    problems = cn.title_problems(title)
    assert any(fragment in p for p in problems), problems


@pytest.mark.parametrize("branch", ["cull-agents", "ci-faster", "harness/run-store", "issue-120"])
def test_good_branches(branch: str) -> None:
    assert cn.branch_problems(branch) == []


@pytest.mark.parametrize(
    "branch",
    ["Cull-Agents", "cull_agents", "cull--agents", "-cull", "cull/", "a" * (cn.MAX_BRANCH + 1)],
)
def test_bad_branches(branch: str) -> None:
    assert cn.branch_problems(branch) != []


def test_main_reports_and_exits(capsys: pytest.CaptureFixture[str]) -> None:
    assert cn.main(["--title", "Add things", "--branch", "Add_Things"]) == 1
    assert len(capsys.readouterr().out.splitlines()) == 2
    assert cn.main(["--title", "feat: things", "--branch", "things"]) == 0


@pytest.mark.parametrize(
    ("title", "branch"),
    [
        (
            "build(deps): Bump jsdom from 29.1.1 to 30.1.2 in /app/web",
            "dependabot/npm_and_yarn/app/web/jsdom-30.1.2",
        ),
        (
            "chore(main): release app 0.3.0-alpha.1",
            "release-please--branches--main--components--app",
        ),
    ],
)
def test_tool_branches_are_exempt(title: str, branch: str) -> None:
    assert cn.branch_problems(branch) != []
    assert cn.main(["--title", title, "--branch", branch]) == 0

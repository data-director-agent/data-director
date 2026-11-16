"""The registration check in scripts/check_members.py: each member is in every hand-kept list."""

from __future__ import annotations

import copy
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_members as cm  # noqa: E402

AGENT = "dd_agent_advisor_dmp"


@pytest.fixture
def config() -> dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


@pytest.fixture
def found(config: dict[str, Any]) -> list[cm.Member]:
    return cm.members(ROOT, config)


def test_the_repository_passes() -> None:
    assert cm.problems() == []


def test_every_agent_is_found(found: list[cm.Member]) -> None:
    agents = {member.path for member in found if member.is_agent}
    assert agents == {
        path.parent.relative_to(ROOT).as_posix() for path in ROOT.glob("agents/*/pyproject.toml")
    }


@pytest.mark.parametrize(
    "drop",
    [
        lambda c: c["tool"]["importlinter"]["root_packages"].remove(AGENT),
        lambda c: c["tool"]["ruff"]["lint"]["isort"]["known-first-party"].remove(AGENT),
        lambda c: c["tool"]["coverage"]["run"]["source_pkgs"].remove(AGENT),
        lambda c: c["tool"]["mypy"]["mypy_path"].remove("agents/advisor-dmp/src"),
        lambda c: c["project"]["dependencies"].remove("data-director-agent-advisor-dmp"),
        lambda c: c["tool"]["uv"]["sources"].pop("data-director-agent-advisor-dmp"),
    ],
    ids=[
        "root_packages",
        "known-first-party",
        "source_pkgs",
        "mypy_path",
        "dependencies",
        "sources",
    ],
)
def test_a_member_missing_from_a_list_is_reported(
    config: dict[str, Any], found: list[cm.Member], drop: Any
) -> None:
    changed = copy.deepcopy(config)
    drop(changed)
    report = cm.pyproject_problems(changed, found)
    assert len(report) == 1
    assert "advisor-dmp" in report[0]


def test_a_contract_naming_some_agents_must_name_all(
    config: dict[str, Any], found: list[cm.Member]
) -> None:
    changed = copy.deepcopy(config)
    independence = next(
        contract
        for contract in changed["tool"]["importlinter"]["contracts"]
        if contract["type"] == "independence"
    )
    independence["modules"].remove(AGENT)
    report = cm.pyproject_problems(changed, found)
    assert len(report) == 1
    assert AGENT in report[0]


def test_an_agent_missing_from_a_deployment_file_is_reported(
    tmp_path: Path, found: list[cm.Member]
) -> None:
    for relative in cm.AGENT_FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")
    assert cm.agent_file_problems(tmp_path, found) == []
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        compose.read_text(encoding="utf-8").replace("advisor-fairness", "advisor-unknown"),
        encoding="utf-8",
    )
    assert cm.agent_file_problems(tmp_path, found) == [
        "compose.yaml: does not name the agent advisor-fairness"
    ]

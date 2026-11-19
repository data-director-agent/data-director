"""Check that every workspace member is registered everywhere the repository lists members by hand.

Each member, and above all each agent, is named in several hand-kept lists: the root
`pyproject.toml` (dependencies, uv sources, Import Linter, Ruff, coverage, mypy) and the
deployment files that start every agent. A member missing from one of them is checked less, or
not deployed, without anything failing. This reports:

- a member missing from a list in the root `pyproject.toml` that names every member;
- an Import Linter contract that names some agents but not all of them, since a rule about
  agents applies to every agent;
- an agent missing from a file in `AGENT_FILES`, which start or register every in-tree agent.

    uv run --no-project --python 3.14 scripts/check_members.py

It prints one problem per line and exits 1 if there is any.
"""

from __future__ import annotations

import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Files that list every in-tree agent by its directory name.
AGENT_FILES = (
    "compose.yaml",
    "docker/agents.yaml",
    "docker/compose.image.yaml",
    "app/config/agents.yaml",
)


@dataclass(frozen=True)
class Member:
    path: str  # The member's directory, from the root, such as `agents/advisor-dmp`.
    distribution: str  # Its `[project].name`.
    package: str  # Its import package, the one directory under `src/`.

    @property
    def is_agent(self) -> bool:
        return self.path.startswith("agents/")


def _requirement_name(requirement: str) -> str:
    return re.split(r"[\[<>=!~; ]", requirement, maxsplit=1)[0]


def members(root: Path, config: dict[str, Any]) -> list[Member]:
    found: list[Member] = []
    for pattern in config["tool"]["uv"]["workspace"]["members"]:
        for directory in sorted(root.glob(pattern)):
            project = directory / "pyproject.toml"
            if not project.is_file():
                continue
            name = tomllib.loads(project.read_text(encoding="utf-8"))["project"]["name"]
            packages = sorted(init.parent.name for init in directory.glob("src/*/__init__.py"))
            if len(packages) != 1:
                raise SystemExit(f"{directory}: expected one package under src/, got {packages}")
            found.append(Member(directory.relative_to(root).as_posix(), name, packages[0]))
    return found


def _contract_lists(contract: dict[str, Any]) -> dict[str, set[str]]:
    """Each list of modules in an Import Linter contract, by a name for it."""
    lists: dict[str, set[str]] = {}
    for key in ("modules", "source_modules", "forbidden_modules"):
        if key in contract:
            lists[key] = set(contract[key])
    for index, layer in enumerate(contract.get("layers", [])):
        lists[f"layer {index + 1}"] = {name.strip() for name in layer.split("|")}
    return lists


def pyproject_problems(config: dict[str, Any], found: list[Member]) -> list[str]:
    tool = config["tool"]
    lists: dict[str, set[str]] = {
        "[project].dependencies": {
            _requirement_name(item) for item in config["project"]["dependencies"]
        },
        "[tool.uv.sources]": set(tool["uv"]["sources"]),
    }
    packages: dict[str, set[str]] = {
        "[tool.importlinter].root_packages": set(tool["importlinter"]["root_packages"]),
        "[tool.ruff.lint.isort].known-first-party": set(
            tool["ruff"]["lint"]["isort"]["known-first-party"]
        ),
        "[tool.coverage.run].source_pkgs": set(tool["coverage"]["run"]["source_pkgs"]),
    }
    mypy_path = set(tool["mypy"]["mypy_path"])
    report: list[str] = []
    for member in found:
        report += [
            f"{member.path}: {member.distribution} is missing from {where}"
            for where, names in lists.items()
            if member.distribution not in names
        ]
        report += [
            f"{member.path}: {member.package} is missing from {where}"
            for where, names in packages.items()
            if member.package not in names
        ]
        if f"{member.path}/src" not in mypy_path:
            report.append(f"{member.path}: {member.path}/src is missing from [tool.mypy].mypy_path")
    agents = {member.package for member in found if member.is_agent}
    for contract in tool["importlinter"]["contracts"]:
        for key, names in _contract_lists(contract).items():
            named = names & agents
            if named and named != agents:
                report += [
                    f"Import Linter contract {contract['name']!r}: {key} names other agents "
                    f"but not {package}"
                    for package in sorted(agents - named)
                ]
    return report


def agent_file_problems(root: Path, found: list[Member]) -> list[str]:
    report: list[str] = []
    for relative in AGENT_FILES:
        text = (root / relative).read_text(encoding="utf-8")
        for member in found:
            if not member.is_agent:
                continue
            name = member.path.removeprefix("agents/")
            if not re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text):
                report.append(f"{relative}: does not name the agent {name}")
    return report


def problems(root: Path = ROOT) -> list[str]:
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    found = members(root, config)
    return pyproject_problems(config, found) + agent_file_problems(root, found)


def main() -> int:
    report = problems()
    for line in report:
        print(line)
    if report:
        print(
            f"{len(report)} registration problem(s); add the member to each list named",
            file=sys.stderr,
        )
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())

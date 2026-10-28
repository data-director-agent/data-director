"""Check that each workspace member keeps to its own directory (ADR-0031).

A member is a package listed in the root `[tool.uv.workspace]`. So that it could move to a
repository of its own, it imports only the first-party packages it declares, and reads no path
outside its directory:

- a module under `src/` imports only the members named in `[project].dependencies` or an extra;
- any other Python file in the member (tests, browser tests, scripts) may also import those in
  the member's `[dependency-groups].dev`;
- no Python file climbs out of the member with `Path(__file__)…parents[N]`;
- every member it requires at run time carries a version, which the workspace ignores but a
  built wheel keeps (RELEASING.md).

The uv workspace installs every member together, so none of this fails at run time; it fails
only when the member is installed on its own.

    uv run --no-project python scripts/check_boundaries.py

Known exceptions are listed in `scripts/boundaries.toml`, each with the issue that removes it.
An exception that no longer occurs is reported too, so the list only shrinks. The script prints
one `path:line: problem` per problem and exits 1 if there is any.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = ROOT / "scripts" / "boundaries.toml"

# A requirement's distribution name, before any extra, marker or version.
REQUIREMENT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# `Path(__file__).resolve().parents[N]` or `Path(__file__).parents[N]`.
PARENTS = re.compile(r"__file__\)(?:\.resolve\(\))?\.parents\[(\d+)\]")


@dataclass(frozen=True)
class Member:
    """A workspace member: its directory, distribution name and declared requirements."""

    path: str
    name: str
    modules: frozenset[str]
    runtime: frozenset[str]
    dev: frozenset[str]
    # Runtime requirements with no version specifier.
    unversioned: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Problem:
    path: str
    line: int
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.detail}"


def normalise(name: str) -> str:
    """A distribution name as packaging compares them (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_names(requirements: list[str]) -> set[str]:
    names = set()
    for requirement in requirements:
        match = REQUIREMENT_NAME.match(requirement.strip())
        if match:
            names.add(normalise(match.group()))
    return names


def unversioned(requirements: list[str]) -> set[str]:
    """The names in `requirements` that carry no version specifier."""
    names = set()
    for requirement in requirements:
        match = REQUIREMENT_NAME.match(requirement.strip())
        rest = requirement.strip()[match.end() :] if match else ""
        rest = re.sub(r"^\[[^\]]*\]", "", rest.strip()).split(";")[0]
        if match and not rest.strip():
            names.add(normalise(match.group()))
    return names


def member_dirs(root: Path = ROOT) -> list[Path]:
    workspace = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = workspace["tool"]["uv"]["workspace"]["members"]
    return sorted(
        path
        for pattern in patterns
        for path in root.glob(pattern)
        if (path / "pyproject.toml").is_file()
    )


def read_member(directory: Path, root: Path = ROOT) -> Member:
    project_file = tomllib.loads((directory / "pyproject.toml").read_text(encoding="utf-8"))
    project = project_file["project"]
    runtime = requirement_names(project.get("dependencies", []))
    loose = unversioned(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        runtime |= requirement_names(extra)
        loose |= unversioned(extra)
    dev = requirement_names(project_file.get("dependency-groups", {}).get("dev", []))
    src = directory / "src"
    modules = (
        frozenset(p.name for p in src.iterdir() if p.is_dir()) if src.is_dir() else frozenset()
    )
    return Member(
        path=directory.relative_to(root).as_posix(),
        name=normalise(project["name"]),
        modules=modules,
        runtime=frozenset(runtime),
        dev=frozenset(dev),
        unversioned=frozenset(loose),
    )


def imports(source: str) -> list[tuple[int, str]]:
    """`(line, top-level module)` for each absolute import in `source`."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name.split(".")[0]) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.lineno, node.module.split(".")[0]))
    return found


def climbs_out(relative: str, member: str, source: str) -> list[tuple[int, int]]:
    """`(line, N)` for each `parents[N]` in the file at `relative` that leaves `member`.

    `parents[N]` of a file `member/a/b.py` is `member/a` for N = 0 and `member` for N = 1, so it
    leaves the member once N exceeds the number of directories between the two.
    """
    depth = len(Path(relative).relative_to(member).parts) - 1
    return [
        (number, int(match.group(1)))
        for number, line in enumerate(source.splitlines(), start=1)
        for match in PARENTS.finditer(line)
        if int(match.group(1)) > depth
    ]


def file_problems(
    relative: str, member: Member, owners: dict[str, str], source: str
) -> list[Problem]:
    """What the file at `relative`, in `member`, imports or reads that it does not declare."""
    in_src = relative.startswith(f"{member.path}/src/")
    allowed = {member.name} | member.runtime | (set() if in_src else member.dev)
    scope = "dependencies" if in_src else "dependencies or dev group"
    problems = [
        Problem(relative, number, f"imports {module} ({owners[module]}), not in its {scope}")
        for number, module in imports(source)
        if module in owners and owners[module] not in allowed
    ]
    problems += [
        Problem(relative, number, f"reads outside {member.path}/ (parents[{n}])")
        for number, n in climbs_out(relative, member.path, source)
    ]
    return problems


def tracked_python(member: str, root: Path = ROOT) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", f"{member}/*.py"],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
    )
    return [path for path in out.stdout.split("\0") if path]


def load_allowed(path: Path = ALLOWED) -> set[tuple[str, str]]:
    """`(path, detail prefix)` for each known exception."""
    if not path.is_file():
        return set()
    entries = tomllib.loads(path.read_text(encoding="utf-8")).get("exception", [])
    return {(entry["path"], entry["problem"]) for entry in entries}


def is_allowed(problem: Problem, allowed: set[tuple[str, str]]) -> tuple[str, str] | None:
    for entry in allowed:
        if problem.path == entry[0] and problem.detail.startswith(entry[1]):
            return entry
    return None


def problems(root: Path = ROOT, allowed: set[tuple[str, str]] | None = None) -> list[str]:
    allowed = load_allowed() if allowed is None else allowed
    members = [read_member(directory, root) for directory in member_dirs(root)]
    owners = {module: member.name for member in members for module in member.modules}
    first_party = {member.name for member in members}
    found: list[Problem] = []
    for member in members:
        pyproject = f"{member.path}/pyproject.toml"
        lines = (root / pyproject).read_text(encoding="utf-8").splitlines()
        found += [
            Problem(
                pyproject,
                next((i for i, line in enumerate(lines, start=1) if f'"{name}' in line), 1),
                f"requires {name} without a version",
            )
            for name in sorted(member.unversioned & first_party)
        ]
        for relative in tracked_python(member.path, root):
            try:
                source = (root / relative).read_text(encoding="utf-8")
            except FileNotFoundError:
                continue  # Deleted in the working tree.
            found += file_problems(relative, member, owners, source)
    found.sort(key=lambda problem: (problem.path, problem.line))
    used = {entry for problem in found if (entry := is_allowed(problem, allowed))}
    report = [str(problem) for problem in found if not is_allowed(problem, allowed)]
    report += [
        f"{path}: no longer {detail!r}; remove it from {ALLOWED.relative_to(ROOT)}"
        for path, detail in sorted(allowed - used)
    ]
    return report


def main() -> int:
    report = problems()
    for line in report:
        print(line)
    if report:
        print(
            f"{len(report)} boundary problem(s); declare the package, or see ADR-0031",
            file=sys.stderr,
        )
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())

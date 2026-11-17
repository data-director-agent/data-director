"""`dd.py new-agent NAME`: write a new agent package from a template, and register it.

An agent is a workspace member, and the repository lists its members by hand in several places
(scripts/check_members.py, scripts/check_deploy.py). This writes the package from
`templates/agent/`, which uses the agent kit in `dd_sdk.agent`, then lists the new agent wherever
the worked example, `example-hello`, is listed: a member missing from any list fails
`check_members.py`, so `example-hello` is in every one of them. Each new entry is a copy of
`example-hello`'s, with the names and the port changed.

What it then runs (the schema generator, Ruff and `uv lock`) is passed in, so that tests can write
an agent into a copy of the repository without a network.
"""

from __future__ import annotations

import os
import re
import string
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ddtool.common import DevError

TEMPLATE = Path(__file__).resolve().parent / "templates" / "agent"

# The agent every list names, whose entries are copied for a new agent.
REFERENCE = "example-hello"

# The files that list agents, other than the root pyproject.toml, by the form of their lists.
YAML_FILES = (
    "compose.yaml",
    "docker/compose.image.yaml",
    "docker/agents.yaml",
    "app/config/agents.yaml",
    "workbench/agents.yaml",
    "app/config/profile.yaml.example",
    "workbench/profiles/default.yaml",
    "harness/src/dd_harness/testing/profiles/test-permissive.yaml",
)
ENV_DIR = "deploy/agents"
MKDOCS = "mkdocs.yml"
# The roster table that gives every agent one state (scripts/tests/test_roster.py). A new agent is
# a mock until its author moves it.
ROSTER = "docs/specs/agents.md"
ROSTER_ROW = re.compile(r"^(\| Mock\b[^|]*\|)([^|]*)\|$", re.MULTILINE)
PORTS_FROM = "app/config/agents.yaml"

NAME = re.compile(r"^[a-z][a-z0-9]*(-[a-z][a-z0-9]*)+$")


@dataclass(frozen=True)
class Names:
    """Every name a new agent goes by, derived from its directory name."""

    name: str  # The directory under agents/ and the service name, such as `advisor-foo`.
    port: int

    @property
    def snake(self) -> str:
        return self.name.replace("-", "_")

    @property
    def package(self) -> str:
        return f"dd_agent_{self.snake}"

    @property
    def distribution(self) -> str:
        return f"data-director-agent-{self.name}"

    @property
    def script(self) -> str:
        return f"dd-{self.name}"

    @property
    def agent_id(self) -> str:
        """`advisor-foo` is `advisor.foo`, as `example-hello` is `example.hello`."""
        return self.name.replace("-", ".", 1)

    @property
    def agent_class(self) -> str:
        return "".join(part.capitalize() for part in self.name.split("-"))

    @property
    def title(self) -> str:
        return " ".join(part.capitalize() for part in self.name.split("-"))

    def substitutions(self, authors: str) -> dict[str, str]:
        return {
            "name": self.name,
            "package": self.package,
            "distribution": self.distribution,
            "script": self.script,
            "agent_id": self.agent_id,
            "agent_class": self.agent_class,
            "input_class": f"{self.agent_class}Request",
            "payload_class": f"{self.agent_class}Advice",
            "title": self.title,
            "port": str(self.port),
            "authors": authors,
        }


REFERENCE_NAMES = Names(REFERENCE, port=0)


def check_name(name: str) -> None:
    if not NAME.match(name):
        raise DevError(
            f"{name!r} is not an agent name: lower-case words joined by hyphens, at least two, "
            "such as advisor-foo (its agent id is then advisor.foo)"
        )


def next_port(root: Path) -> int:
    """One more than the highest port the app lists an agent on."""
    text = (root / PORTS_FROM).read_text(encoding="utf-8")
    ports = [int(port) for port in re.findall(r"url:\s*\S+:(\d+)", text)]
    if not ports:
        raise DevError(f"{PORTS_FROM} lists no agent with a port")
    return max(ports) + 1


def _reference_port(root: Path) -> int:
    text = (root / PORTS_FROM).read_text(encoding="utf-8")
    found = re.search(rf"- name: {REFERENCE}\s*\n\s*url:\s*\S+:(\d+)", text)
    if found is None:
        raise DevError(f"{PORTS_FROM} does not list {REFERENCE} with a port")
    return int(found.group(1))


# --- Writing the package -------------------------------------------------------------------------


def _target(relative: Path, names: Names) -> Path:
    parts = [names.package if part == "package" else part for part in relative.parts]
    name = parts[-1].removesuffix(".tmpl")
    if name == "schema.yaml":
        name = f"{names.name}.yaml"
    elif name == "test_agent.py":
        # Test modules are imported by basename, so each must be unique across the workspace.
        name = f"test_{names.snake}.py"
    return Path(*parts[:-1], name)


def write_package(root: Path, names: Names) -> Path:
    directory = root / "agents" / names.name
    if directory.exists():
        raise DevError(f"agents/{names.name} already exists")
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    authors = ", ".join(
        "{ " + ", ".join(f'{key} = "{value}"' for key, value in author.items()) + " }"
        for author in config["project"].get("authors", [])
    )
    values = names.substitutions(f"[{authors}]")
    for source in sorted(TEMPLATE.rglob("*.tmpl")):
        target = directory / _target(source.relative_to(TEMPLATE), names)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = string.Template(source.read_text(encoding="utf-8")).substitute(values)
        target.write_text(text, encoding="utf-8")
    return directory


# --- Registering it ------------------------------------------------------------------------------


def _replace_names(text: str, old: Names, old_port: int, new: Names) -> str:
    text = text.replace(old.script, new.script)
    text = re.sub(rf"(?<![\w-]){re.escape(old.name)}(?![\w-])", new.name, text)
    text = text.replace(old.snake, new.snake).replace(old.agent_id, new.agent_id)
    return re.sub(rf"(?<!\d){old_port}(?!\d)", str(new.port), text)


def _mentions(line: str, port: int) -> bool:
    return bool(
        re.search(rf"(?<![\w-]){REFERENCE}(?![\w-])", line)
        or REFERENCE_NAMES.agent_id in line
        or re.search(rf":{port}(?!\d)", line)
    )


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def clone_yaml_entries(text: str, port: int, new: Names) -> str:
    """Copy each YAML entry that names the reference agent, after it, for `new`.

    An entry is the line that names the agent and every line under it indented further, as in a
    list item (`- name: example-hello` and its `url:`) or a mapping (a Compose service).
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not _mentions(line, port) or line.lstrip().startswith("#"):
            out.append(line)
            index += 1
            continue
        start, indent = index, _indent(line)
        # A list item's own keys sit two columns in from its dash.
        child = indent + 2 if line.lstrip().startswith("- ") else indent + 1
        index += 1
        while index < len(lines) and lines[index].strip() and _indent(lines[index]) >= child:
            index += 1
        block = lines[start:index]
        out += block
        clone = [_replace_names(b, REFERENCE_NAMES, port, new) for b in block]
        if not clone[-1].endswith("\n"):
            clone[-1] += "\n"
        # Entries separated by a blank line (Compose services) stay separated.
        if index < len(lines) and not lines[index].strip():
            out += ["\n", *clone]
        else:
            out += clone
    return "".join(out)


def clone_pyproject_entries(text: str, new: Names) -> str:
    """List `new` wherever the root pyproject.toml lists the reference agent."""
    old = REFERENCE_NAMES
    tokens = {
        old.distribution: new.distribution,
        old.package: new.package,
        f"agents/{old.name}/src": f"agents/{new.name}/src",
    }
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        found = [
            token for token in tokens if re.search(rf"(?<![\w-]){re.escape(token)}(?![\w-])", line)
        ]
        if not found or line.lstrip().startswith("#"):
            out.append(line)
            continue
        token = found[0]
        stripped = line.strip()
        if stripped in {f'"{token}",', f'"{token}"'} or stripped.startswith(f"{token} = "):
            # One entry to a line: an array item, or a [tool.uv.sources] key.
            out += [line, line.replace(token, tokens[token])]
        elif f'"{token}"' in line:
            out.append(line.replace(f'"{token}"', f'"{token}", "{tokens[token]}"', 1))
        else:
            # A name in an Import Linter layer, `a | b | c`.
            out.append(
                re.sub(
                    rf"(?<![\w-]){re.escape(token)}(?![\w-])",
                    f"{token} | {tokens[token]}",
                    line,
                    count=1,
                )
            )
    return "".join(out)


def add_to_docs_nav(text: str, new: Names) -> str:
    """List the agent's README in the site's navigation, after the last agent's README."""
    lines = text.splitlines(keepends=True)
    readmes = [
        i for i, line in enumerate(lines) if re.search(r"/agents/[\w-]+/README\.md\s*$", line)
    ]
    if not readmes:
        return text
    last = lines[readmes[-1]]
    entry = f"{last[: _indent(last)]}- {new.title}: /agents/{new.name}/README.md\n"
    return "".join([*lines[: readmes[-1] + 1], entry, *lines[readmes[-1] + 1 :]])


def add_to_roster(text: str, new: Names) -> str:
    """Put the agent in the roster table's Mock row, keeping the row's ids in order."""
    row = ROSTER_ROW.search(text)
    if row is None:
        raise DevError(f"{ROSTER} has no Mock row in its roster table")
    ids = sorted({*re.findall(r"`([\w.]+)`", row.group(2)), new.agent_id})
    cell = " " + ", ".join(f"`{agent_id}`" for agent_id in ids) + " "
    return text[: row.start()] + row.group(1) + cell + "|" + text[row.end() :]


def register(root: Path, names: Names) -> list[str]:
    """List the new agent wherever the reference agent is listed; return the files changed."""
    port = _reference_port(root)
    changed: list[str] = []

    def update(relative: str, edit: Callable[[str], str]) -> None:
        path = root / relative
        before = path.read_text(encoding="utf-8")
        after = edit(before)
        if after != before:
            path.write_text(after, encoding="utf-8")
            changed.append(relative)

    update("pyproject.toml", lambda text: clone_pyproject_entries(text, names))
    for relative in YAML_FILES:
        update(relative, lambda text: clone_yaml_entries(text, port, names))
    update(MKDOCS, lambda text: add_to_docs_nav(text, names))
    update(ROSTER, lambda text: add_to_roster(text, names))
    env = root / ENV_DIR / f"{REFERENCE}.env"
    target = f"{ENV_DIR}/{names.name}.env"
    (root / target).write_text(
        _replace_names(env.read_text(encoding="utf-8"), REFERENCE_NAMES, port, names),
        encoding="utf-8",
    )
    changed.append(target)
    return changed


# --- The command ---------------------------------------------------------------------------------

Runner = Callable[[list[str], Path], None]


def run_command(command: list[str], cwd: Path) -> None:
    # dd.py runs in an environment of its own; the commands are for the workspace's.
    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    result = subprocess.run(command, cwd=cwd, env=env, check=False)
    if result.returncode != 0:
        raise DevError(f"`{' '.join(command)}` failed (exit {result.returncode})")


def finish_commands(root: Path, names: Names) -> list[list[str]]:
    """What turns the written files into a member that passes the checks."""
    directory = f"agents/{names.name}"
    schema = f"{directory}/src/{names.package}/schema/{names.name}.yaml"
    return [
        ["uv", "lock"],
        ["uv", "run", "dd-gen-schema", schema],
        # Long names make long lines: format first, then check what is left.
        ["uv", "run", "ruff", "format", "--quiet", directory],
        ["uv", "run", "ruff", "check", "--fix", "--quiet", directory],
    ]


def create(root: Path, name: str, *, run: Runner = run_command, port: int | None = None) -> Names:
    """Write agent `name` into the repository at `root`, register it, and finish it with `run`."""
    check_name(name)
    names = Names(name, port if port is not None else next_port(root))
    write_package(root, names)
    register(root, names)
    for command in finish_commands(root, names):
        run(command, root)
    return names


def new_agent(root: Path, name: str) -> int:
    names = create(root, name)
    print(
        f"Wrote agents/{names.name} ({names.agent_id}, `{names.script}` on port {names.port}) and "
        f"listed it everywhere {REFERENCE} is listed.\n"
        f"Next: edit agents/{names.name}/src/{names.package}/agent.py, then run "
        f"`uv run pytest agents/{names.name}`. agents/README.md has the rest of the recipe."
    )
    return 0

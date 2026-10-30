"""What `setup`, `start` and `doctor` share: the settings files, the agents, the shell's build and
the toolchain."""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from devstack import paths

# The example principal the documentation uses (config/examples/app.env): ORCID's test record.
EXAMPLE_PRINCIPAL = {
    "DD_PRINCIPAL_ID": "https://orcid.org/0000-0002-1825-0097",
    "DD_PRINCIPAL_NAME": "Josiah Carberry",
}
KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_FILE")
# Agents that stop at start-up without a model key, so `start` skips them when they have none.
MODEL_BACKED = {"orchestrator-model"}
NODE_MAJOR = 22  # the oldest Node the shell's toolchain supports (README, "Quick start")
APP_PORT = 7860  # dd_app's default (DD_APP_PORT)
WEB_PORT = 5173  # Vite's default
INSTALL_LINKS = {
    "uv": "https://docs.astral.sh/uv/getting-started/installation/",
    "node": "https://nodejs.org/en/download (version 22 or later)",
    "npm": "https://nodejs.org/en/download (npm comes with Node)",
}
# What the shell's build depends on: newer than app/web/dist/index.html means the build is stale.
WEB_INPUTS = (
    "src",
    "index.html",
    "package.json",
    "package-lock.json",
    "vite.config.ts",
    "tsconfig.json",
)


class DevError(Exception):
    """A problem the person can fix, reported as one line."""


# --- Settings files --------------------------------------------------------------------------


def parse_env(text: str, source: str = "<env>") -> dict[str, str]:
    """A dotenv file's variables, read as `uv run --env-file` reads them.

    An unquoted value with a space in it is refused here, as uv refuses it ("Failed to parse
    environment file"), so `doctor` can name the line.
    """
    values: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").lstrip()
        name, sep, value = line.partition("=")
        name = name.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise DevError(f"{source}, line {number}: expected NAME=value")
        value = value.strip()
        if value[:1] in {'"', "'"}:
            quote = value[0]
            end = value.find(quote, 1)
            if end == -1:
                raise DevError(f"{source}, line {number}: the quote is not closed")
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
            if re.search(r"\s", value):
                raise DevError(
                    f'{source}, line {number}: put quotes round a value with a space: {name}="{value}"'
                )
        values[name] = value
    return values


def read_env(path: Path) -> dict[str, str]:
    """`path`'s variables, or none if there is no such file."""
    if not path.is_file():
        return {}
    return parse_env(path.read_text(encoding="utf-8"), str(path.relative_to(paths.ROOT)))


def _quoted(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:@+-]*", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def update_env(path: Path, updates: dict[str, str], header: str) -> None:
    """Set each of `updates` in `path`, keeping every other line as it was.

    A variable already set is replaced where it stands; a new one is added at the end. A new file
    starts with `header`. The file is readable only by its owner, as it may hold a key.
    """
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else [header]
    pending = dict(updates)
    for i, raw in enumerate(lines):
        name = raw.strip().removeprefix("export ").partition("=")[0].strip()
        if not raw.lstrip().startswith("#") and name in pending:
            lines[i] = f"{name}={_quoted(pending.pop(name))}"
    lines += [f"{name}={_quoted(value)}" for name, value in pending.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600)
    path.chmod(0o600)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _without_key(path: Path) -> dict[str, str]:
    """The settings in `path`, which every agent reads, so it may hold no model key (ADR-0026)."""
    found = read_env(path)
    if leaked := [var for var in KEY_VARS if found.get(var)]:
        raise DevError(
            f"{path.relative_to(paths.ROOT)} sets {leaked[0]}, which every agent would read; "
            f"move it to the agent's own file, config/local/agents/<name>.env (ADR-0026)"
        )
    return found


def app_env() -> dict[str, str]:
    """What the app reads, as under systemd: `config/local/app.env` and nothing of the agents'."""
    return _without_key(paths.APP_ENV)


def agent_env(agent: Agent) -> dict[str, str]:
    """What one agent reads: `agents.env`, then its own file, and the credentials directory.

    It is given neither the app's settings nor another agent's (ADR-0026).
    """
    return (
        _without_key(paths.AGENTS_ENV)
        | read_env(agent.env_file)
        | {"CREDENTIALS_DIRECTORY": str(paths.CREDENTIALS_DIR)}
    )


def has_key(env: dict[str, str]) -> bool:
    return any(env.get(var) for var in KEY_VARS)


def ensure_local_tree() -> list[Path]:
    """Create `config/local/` as deployment has it, from the committed examples. Never overwrites.

    Returns what it created.
    """
    created: list[Path] = []
    for name in ("app.env", "agents.env"):
        dest = paths.LOCAL_DIR / name
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(paths.EXAMPLES_DIR / name, dest)
            dest.chmod(0o600)
            created.append(dest)
    paths.AGENT_ENV_DIR.mkdir(parents=True, exist_ok=True)
    paths.CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    return created


# Where a stray settings file of the old layout moves to (ADR-0026).
OLD_LOCATIONS = {
    ".env": "config/local/app.env (DD_PRINCIPAL_*, DD_APP_*) and config/local/agents.env (the rest)",
    "workbench/.env": "config/local/app.env (DD_PRINCIPAL_*, DD_RUNS_DIR, DD_PROFILE) and "
    "config/local/agents.env (DD_STANDARDS_*, FAIRSHARING_*)",
    "app/.env": "config/local/app.env",
}


def stray_files() -> list[str]:
    """Settings files of the old layout that exist, each with where its settings now go."""
    found = [
        f"{old} -> {new}" for old, new in OLD_LOCATIONS.items() if (paths.ROOT / old).is_file()
    ]
    old_agents = paths.ROOT / "workbench" / "agents"
    found += [
        f"{p.relative_to(paths.ROOT)} -> config/local/agents/{p.name}"
        f" (a model key goes in config/local/credentials/, named by ANTHROPIC_API_KEY_FILE)"
        for p in sorted(old_agents.glob("*.env"))
    ]
    return found


# --- Agents and the shell --------------------------------------------------------------------


@dataclass(frozen=True)
class Agent:
    name: str
    port: int

    @property
    def script(self) -> str:
        return f"dd-{self.name}"

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def env_file(self) -> Path:
        return paths.AGENT_ENV_DIR / f"{self.name}.env"


def load_agents(path: Path | None = None) -> list[Agent]:
    """The agents the app reaches, from its agent list, each on the port its URL names."""
    text = (path or paths.AGENTS_CONFIG).read_text(encoding="utf-8")
    entries = yaml.safe_load(text)["agents"]
    return [Agent(e["name"], urlsplit(e["url"]).port or 80) for e in entries]


def _newest(files: Iterable[Path]) -> float:
    newest = 0.0
    for path in files:
        if path.is_dir():
            newest = max([newest, *(p.stat().st_mtime for p in path.rglob("*") if p.is_file())])
        elif path.is_file():
            newest = max(newest, path.stat().st_mtime)
    return newest


def needs_install(web: Path | None = None) -> bool:
    """Whether `node_modules` is missing or older than the lock file."""
    web = web or paths.WEB
    modules = web / "node_modules"
    return (
        not modules.is_dir()
        or modules.stat().st_mtime < (web / "package-lock.json").stat().st_mtime
    )


def needs_build(web: Path | None = None) -> bool:
    """Whether the built shell is missing or older than anything it is built from."""
    web = web or paths.WEB
    built = web / "dist" / "index.html"
    return not built.is_file() or built.stat().st_mtime < _newest(web / p for p in WEB_INPUTS)


def workspace_env() -> dict[str, str]:
    """This environment less `VIRTUAL_ENV`: `uv run` gives this script an environment of its own,
    and what it starts uses the workspace's `.venv`."""
    return {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    if subprocess.run(cmd, cwd=cwd or paths.ROOT, env=workspace_env()).returncode != 0:
        raise DevError(f"`{' '.join(cmd)}` failed; its output is above")


def prepare_web(web: Path | None = None) -> None:
    """Install the shell's packages and build it, if either is out of date."""
    web = web or paths.WEB
    if needs_install(web):
        run(["npm", "ci"], cwd=web)
        (web / "node_modules").touch()
    if needs_build(web):
        run(["npm", "run", "build"], cwd=web)


def port_free(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except OSError:
        return False


# --- Toolchain -------------------------------------------------------------------------------


def tool_problems() -> list[str]:
    """What is missing from the toolchain, each with where to get it. Python comes with uv."""
    problems = [
        f"{tool} is not installed: {INSTALL_LINKS[tool]}"
        for tool in ("uv", "node", "npm")
        if not shutil.which(tool)
    ]
    if shutil.which("node"):
        version = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout
        major = int(m[1]) if (m := re.match(r"v(\d+)", version)) else 0
        if major < NODE_MAJOR:
            problems.append(f"Node {version.strip() or '?'} is too old: {INSTALL_LINKS['node']}")
    return problems

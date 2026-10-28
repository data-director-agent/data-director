# /// script
# requires-python = ">=3.14"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Set up and run the Data Director development stack from one terminal.

    uv run scripts/dev.py setup     # asks for your settings, writes them, installs, builds
    uv run scripts/dev.py start     # the agents, the app and the shell's dev server; Ctrl-C stops all
    uv run scripts/dev.py doctor    # checks the toolchain, the settings and the ports; changes nothing

`setup` writes each setting where it belongs, so nobody has to edit a settings file by hand:

- `.env` at the repository root: whom runs act for. `start` and Docker Compose both read it.
- `workbench/agents/<name>.env`: an agent's own settings and its model key. A key goes only in the
  file of the agent that uses it, never in a file every agent reads (ADR-0026).
- `app/config/profile.yaml`: the local copy of the profile, if the model-backed orchestrator is to
  hold the conversation.

This is a development convenience. The app and the harness stay as strict as they are: only this
script falls back to the example principal when none is set, and it says so. `start` reads the
agents and their ports from `app/config/agents.yaml`; agent `<name>` is served by `dd-<name>`.
POSIX only; on Windows, use WSL.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROOT_ENV = ROOT / ".env"
WORKBENCH_ENV = ROOT / "workbench" / ".env"
AGENT_ENV_DIR = ROOT / "workbench" / "agents"
AGENTS_CONFIG = ROOT / "app" / "config" / "agents.yaml"
PROFILE_EXAMPLE = ROOT / "app" / "config" / "profile.yaml.example"
PROFILE = ROOT / "app" / "config" / "profile.yaml"
WEB = ROOT / "app" / "web"

# The example principal the documentation uses (docker/env.example): ORCID's test record.
EXAMPLE_PRINCIPAL = {
    "DD_PRINCIPAL_ID": "https://orcid.org/0000-0002-1825-0097",
    "DD_PRINCIPAL_NAME": "Josiah Carberry",
}
KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_FILE")
# Agents that stop at start-up without a model key, so `start` skips them when they have none.
MODEL_BACKED = {"orchestrator"}
KEYS_URL = "https://console.anthropic.com/settings/keys"
NODE_MAJOR = 22  # the oldest Node the shell's toolchain supports (README, "Quick start")
APP_PORT = 7860  # dd_app's default (DD_APP_PORT)
WEB_PORT = 5173  # Vite's default
# How long a service may take to answer for the first time: `uv run` may first build the package.
START_TIMEOUT_S = 120
STOP_TIMEOUT_S = 10
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
ORCID_ID = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


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
    return parse_env(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))


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


def mask(secret: str) -> str:
    """Enough of a key to recognise it, and no more."""
    return f"{secret[:3]}…{secret[-4:]}" if len(secret) > 12 else "…"


def principal_id(answer: str) -> str:
    """An ORCID iD as an IRI. A bare iD is given its prefix; another absolute IRI is kept."""
    answer = answer.strip()
    if ORCID_ID.match(answer):
        return f"https://orcid.org/{answer}"
    scheme = urlsplit(answer).scheme
    if (scheme in {"http", "https"} and urlsplit(answer).netloc) or scheme in {"urn", "mailto"}:
        return answer
    raise DevError("give an ORCID iD (0000-0002-1825-0097) or another absolute IRI")


def shared_env() -> dict[str, str]:
    """What every agent and the app read: `workbench/.env`, then the root `.env`, which wins.

    Neither may hold a model key: every agent would be given it (ADR-0026).
    """
    values: dict[str, str] = {}
    for path in (WORKBENCH_ENV, ROOT_ENV):
        found = read_env(path)
        if leaked := [var for var in KEY_VARS if found.get(var)]:
            raise DevError(
                f"{path.relative_to(ROOT)} sets {leaked[0]}, which every agent would read; "
                f"move it to the agent's own file, workbench/agents/<name>.env (ADR-0026)"
            )
        values |= found
    return values


def has_key(env: dict[str, str]) -> bool:
    return any(env.get(var) for var in KEY_VARS)


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
        return AGENT_ENV_DIR / f"{self.name}.env"


def load_agents(path: Path = AGENTS_CONFIG) -> list[Agent]:
    """The agents the app reaches, from its agent list, each on the port its URL names."""
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))["agents"]
    return [Agent(e["name"], urlsplit(e["url"]).port or 80) for e in entries]


def _newest(paths: Iterable[Path]) -> float:
    newest = 0.0
    for path in paths:
        if path.is_dir():
            newest = max([newest, *(p.stat().st_mtime for p in path.rglob("*") if p.is_file())])
        elif path.is_file():
            newest = max(newest, path.stat().st_mtime)
    return newest


def needs_install(web: Path = WEB) -> bool:
    """Whether `node_modules` is missing or older than the lock file."""
    modules = web / "node_modules"
    return (
        not modules.is_dir()
        or modules.stat().st_mtime < (web / "package-lock.json").stat().st_mtime
    )


def needs_build(web: Path = WEB) -> bool:
    """Whether the built shell is missing or older than anything it is built from."""
    built = web / "dist" / "index.html"
    return not built.is_file() or built.stat().st_mtime < _newest(web / p for p in WEB_INPUTS)


def run(cmd: list[str], cwd: Path = ROOT) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    if subprocess.run(cmd, cwd=cwd).returncode != 0:
        raise DevError(f"`{' '.join(cmd)}` failed; its output is above")


def prepare_web(web: Path = WEB) -> None:
    """Install the shell's packages and build it, if either is out of date."""
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


# --- setup -----------------------------------------------------------------------------------


@dataclass
class Prompter:
    """Asks the person questions. Tests give it scripted answers."""

    ask: Callable[[str], str] = input
    ask_secret: Callable[[str], str] = getpass.getpass
    accept_defaults: bool = False

    def text(self, question: str, default: str) -> str:
        if self.accept_defaults:
            return default
        return self.ask(f"{question} [{default}]: ").strip() or default

    def secret(self, question: str) -> str:
        return "" if self.accept_defaults else self.ask_secret(f"{question}: ").strip()

    def yes(self, question: str, default: bool) -> bool:
        if self.accept_defaults:
            return default
        answer = self.ask(f"{question} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
        return default if not answer else answer.startswith("y")


@dataclass
class Changes:
    written: list[Path] = field(default_factory=list)

    def note(self, path: Path) -> None:
        if path not in self.written:
            self.written.append(path)


def ask_principal(prompt: Prompter, changes: Changes) -> None:
    current = {**EXAMPLE_PRINCIPAL, **read_env(ROOT_ENV)}
    print(
        "\nWhom runs act for. There is no sign-in yet, so every run is recorded as acting for this\n"
        "person (ADR-0018). Give your own name and ORCID iD, or press Enter to keep the value shown."
    )
    name = prompt.text("Your name", current["DD_PRINCIPAL_NAME"])
    while True:
        try:
            iri = principal_id(prompt.text("Your ORCID iD", current["DD_PRINCIPAL_ID"]))
            break
        except DevError as exc:
            if prompt.accept_defaults:
                raise
            print(f"  {exc}")
    update_env(
        ROOT_ENV,
        {"DD_PRINCIPAL_NAME": name, "DD_PRINCIPAL_ID": iri},
        "# Written by `uv run scripts/dev.py setup`; read by `dev.py start` and Docker Compose.\n"
        "# Never put a model key here: every agent reads this file (ADR-0026).",
    )
    changes.note(ROOT_ENV)


def ask_model_key(prompt: Prompter, changes: Changes) -> bool:
    """Ask for a model key and give it to the agents that use one. Whether one is set."""
    orchestrator = AGENT_ENV_DIR / "orchestrator.env"
    current = read_env(orchestrator).get("ANTHROPIC_API_KEY", "")
    print(
        "\nAn Anthropic API key (optional). Without one, the home page talks to director.stub, a\n"
        "rule-based agent, and everything else works. With one, the model-backed orchestrator can\n"
        f"hold the conversation. Create a key at {KEYS_URL}. It is stored only in the files of\n"
        "the agents that use it (workbench/agents/), which git ignores."
    )
    shown = f"Enter keeps {mask(current)}" if current else "Enter skips"
    key = prompt.secret(f"Anthropic API key ({shown})") or current
    if not key:
        return False
    header = "# Written by `uv run scripts/dev.py setup`: this agent's own settings (ADR-0026)."
    if key != current:
        update_env(orchestrator, {"ANTHROPIC_API_KEY": key}, header)
        changes.note(orchestrator)
    if prompt.yes("Let the standards advisor use the model to explain its advice too?", False):
        standards = AGENT_ENV_DIR / "standards.env"
        update_env(
            standards, {"DD_STANDARDS_EXPLAINER": "anthropic", "ANTHROPIC_API_KEY": key}, header
        )
        changes.note(standards)
    return True


def use_model_orchestrator(changes: Changes) -> None:
    """Name `orchestrator.model` in the local profile, raising its version (app/README.md)."""
    text = (PROFILE if PROFILE.is_file() else PROFILE_EXAMPLE).read_text(encoding="utf-8")
    if re.search(r"^orchestrator:\s*orchestrator\.model\s*$", text, re.MULTILINE):
        return
    text, named = re.subn(
        r"^orchestrator:.*$", "orchestrator: orchestrator.model", text, flags=re.M
    )
    version = re.search(r"^version:\s*(\d+)", text, re.MULTILINE)
    if not named or not version:
        raise DevError(f"{PROFILE.relative_to(ROOT)} has no `orchestrator` or `version` to change")
    text = text.replace(version[0], f"version: {int(version[1]) + 1}", 1)
    PROFILE.write_text(text, encoding="utf-8")
    changes.note(PROFILE)


def setup(prompt: Prompter, install: bool = True) -> int:
    problems = tool_problems() if install else []
    for problem in problems:
        print(f"missing: {problem}")
    changes = Changes()
    ask_principal(prompt, changes)
    if ask_model_key(prompt, changes) and prompt.yes(
        "Make the model-backed orchestrator the one the home page talks to?", True
    ):
        use_model_orchestrator(changes)
    print("\nWrote " + ", ".join(str(p.relative_to(ROOT)) for p in changes.written) + ".")
    if problems:
        print("Install what is missing above, then run setup again to install and build.")
        return 1
    if install:
        print()
        run(["uv", "sync", "--all-packages", "--all-extras"])
        prepare_web()
    print("\nReady. Start everything with:  uv run scripts/dev.py start")
    return 0


# --- start -----------------------------------------------------------------------------------


@dataclass
class Service:
    name: str
    cmd: list[str]
    env: dict[str, str]
    cwd: Path = ROOT
    proc: subprocess.Popen[str] | None = None


class Stack:
    """Processes started together, their output prefixed by name, and stopped together."""

    def __init__(self) -> None:
        self.services: list[Service] = []
        self._lock = threading.Lock()
        self._width = 0

    def start(self, service: Service) -> None:
        self._width = max(self._width, len(service.name))
        service.proc = subprocess.Popen(
            service.cmd,
            cwd=service.cwd,
            env=service.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            # Its own process group, so stopping it stops what it started too (npm starts node).
            start_new_session=True,
        )
        self.services.append(service)
        threading.Thread(target=self._relay, args=(service,), daemon=True).start()

    def say(self, name: str, line: str) -> None:
        with self._lock:
            print(f"[{name.ljust(self._width)}] {line}", flush=True)

    def _relay(self, service: Service) -> None:
        assert service.proc and service.proc.stdout
        for line in service.proc.stdout:
            self.say(service.name, line.rstrip())
        self.say(service.name, f"exited with code {service.proc.wait()}")

    def wait_for(self, service: Service, url: str) -> bool:
        """Whether `url` answers before `service` exits or the time runs out."""
        deadline = time.monotonic() + START_TIMEOUT_S
        while time.monotonic() < deadline:
            if answers(url):
                return True
            if service.proc is None or service.proc.poll() is not None:
                return False
            time.sleep(0.5)
        self.say(service.name, f"did not answer at {url} within {START_TIMEOUT_S}s")
        return False

    def running(self) -> Iterator[Service]:
        return (s for s in self.services if s.proc and s.proc.poll() is None)

    def stop(self) -> None:
        for service in self.running():
            assert service.proc
            with suppress(ProcessLookupError):
                os.killpg(service.proc.pid, signal.SIGTERM)
        deadline = time.monotonic() + STOP_TIMEOUT_S
        for service in self.services:
            assert service.proc
            try:
                service.proc.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                with suppress(ProcessLookupError):
                    os.killpg(service.proc.pid, signal.SIGKILL)


def start(agents_only: bool, web: bool) -> int:
    # `uv run` gives this script an environment of its own; the services use the workspace's.
    base = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"} | shared_env()
    if not (base.get("DD_PRINCIPAL_ID") and base.get("DD_PRINCIPAL_NAME")):
        base |= EXAMPLE_PRINCIPAL
        print(
            f"No principal is set, so runs act for the example, {EXAMPLE_PRINCIPAL['DD_PRINCIPAL_NAME']}. "
            "Run `uv run scripts/dev.py setup` to give your own."
        )
    agents = load_agents()
    ports = [a.port for a in agents] + (
        [] if agents_only else [APP_PORT] + ([WEB_PORT] if web else [])
    )
    if taken := [p for p in ports if not port_free(p)]:
        raise DevError(
            f"port {', '.join(map(str, taken))} is in use; stop whatever holds it "
            "(an earlier `start`, `scripts/run-agents.sh` or Docker Compose?)"
        )
    if not agents_only:
        prepare_web()

    stack = Stack()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # stop the stack as Ctrl-C does
    try:
        started: list[tuple[Agent, Service]] = []
        for agent in agents:
            env = base | read_env(agent.env_file)
            if agent.name in MODEL_BACKED and not has_key(env):
                print(
                    f"skip  {agent.script}: no model key "
                    f"(run setup, or set it in {agent.env_file.relative_to(ROOT)})"
                )
                continue
            service = Service(
                agent.name, ["uv", "run", agent.script, "serve", "--port", str(agent.port)], env
            )
            stack.start(service)
            started.append((agent, service))
        for agent, service in started:
            if stack.wait_for(service, f"{agent.url}/.well-known/agent-card.json"):
                stack.say(agent.name, f"ready at {agent.url}")

        if not agents_only:
            app = Service(
                "app",
                ["uv", "run", "data-director"],
                # The app opens a browser on its own address; the page to open is printed below.
                base | {"BROWSER": "true"} | read_env(ROOT / "app" / ".env"),
            )
            stack.start(app)
            if not stack.wait_for(app, f"http://127.0.0.1:{APP_PORT}/api/agents"):
                raise DevError("the app did not start; its output is above")
            if web:
                vite = Service(
                    "web",
                    ["npm", "run", "dev"],
                    base | {"DD_APP_URL": f"http://127.0.0.1:{APP_PORT}"},
                    WEB,
                )
                stack.start(vite)
                stack.wait_for(vite, f"http://127.0.0.1:{WEB_PORT}/")
            where = (
                f"http://localhost:{WEB_PORT} (reloads as you edit the shell)"
                if web
                else f"http://127.0.0.1:{APP_PORT}"
            )
            print(f"\nOpen {where}. Ctrl-C stops everything.\n", flush=True)
        else:
            print("\nThe agents are running. Ctrl-C stops them.\n", flush=True)

        while any(True for _ in stack.running()):
            time.sleep(0.5)
        return 1  # every process exited by itself
    except KeyboardInterrupt:
        return 0
    finally:
        # A second signal (uv forwards the one it gets) must not cut the stopping short.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        stack.stop()


# --- doctor ----------------------------------------------------------------------------------


def doctor() -> int:
    problems = tool_problems()
    for path in [
        WORKBENCH_ENV,
        ROOT_ENV,
        ROOT / "app" / ".env",
        *sorted(AGENT_ENV_DIR.glob("*.env")),
    ]:
        try:
            read_env(path)
        except DevError as exc:
            problems.append(str(exc))
    try:
        env = {**os.environ, **shared_env()}
        if not (env.get("DD_PRINCIPAL_ID") and env.get("DD_PRINCIPAL_NAME")):
            print(
                "note: no principal is set; `start` will use the example (run setup to set yours)"
            )
    except DevError as exc:
        problems.append(str(exc))
    for agent in load_agents():
        if agent.name in MODEL_BACKED and not has_key(read_env(agent.env_file) | dict(os.environ)):
            print(f"note: {agent.script} has no model key, so `start` will skip it")
    if needs_install() or needs_build():
        print("note: the shell is not built or is out of date; `start` will build it")

    agents = load_agents()
    busy = [a.port for a in agents if not port_free(a.port)] + [
        p for p in (APP_PORT, WEB_PORT) if not port_free(p)
    ]
    if busy:
        print(f"note: port {', '.join(map(str, busy))} in use (is the stack running?)")
    if answers(f"http://127.0.0.1:{APP_PORT}/api/agents"):
        with urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/api/agents", timeout=10) as resp:
            listing: dict[str, Any] = yaml.safe_load(resp.read())
        for url, reason in dict(listing.get("unavailable") or {}).items():
            problems.append(f"the app cannot reach {url}: {reason}")

    for problem in problems:
        print(f"problem: {problem}")
    print("All good." if not problems else f"{len(problems)} problem(s).")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    setup_cmd = commands.add_parser(
        "setup", help="ask for your settings, write them, install and build"
    )
    setup_cmd.add_argument("--yes", action="store_true", help="accept every default without asking")
    setup_cmd.add_argument("--no-install", action="store_true", help="write the settings only")
    start_cmd = commands.add_parser(
        "start", help="run the agents, the app and the shell's dev server"
    )
    start_cmd.add_argument(
        "--agents-only", action="store_true", help="only the agents (for the workbench)"
    )
    start_cmd.add_argument(
        "--no-web", action="store_true", help="no Vite dev server; use the built shell"
    )
    commands.add_parser("doctor", help="check the toolchain, settings and ports; change nothing")
    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            return setup(Prompter(accept_defaults=args.yes), install=not args.no_install)
        if args.command == "start":
            return start(agents_only=args.agents_only, web=not args.no_web)
        return doctor()
    except DevError as exc:
        print(f"dev.py: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt, EOFError:
        print()
        return 130


if __name__ == "__main__":
    sys.exit(main())

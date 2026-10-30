"""`dev.py start`: run the agents, the app and the shell's dev server; Ctrl-C stops them all."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from devstack import paths
from devstack.common import (
    APP_PORT,
    EXAMPLE_PRINCIPAL,
    MODEL_BACKED,
    WEB_PORT,
    Agent,
    DevError,
    agent_env,
    answers,
    app_env,
    ensure_local_tree,
    has_key,
    load_agents,
    omissions_note,
    port_free,
    prepare_web,
    profile_omissions,
    workspace_env,
)

# How long a service may take to answer for the first time: `uv run` may first build the package.
START_TIMEOUT_S = 120
STOP_TIMEOUT_S = 10


@dataclass
class Service:
    name: str
    cmd: list[str]
    env: dict[str, str]
    cwd: Path = paths.ROOT
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


def start(agents_only: bool, web: bool, reload: bool = True) -> int:
    ensure_local_tree()
    base = workspace_env()
    app = app_env()
    # An app that signs people in acts for no operator, and refuses one (ADR-0029).
    if app.get("DD_OIDC_ISSUER"):
        print(f"The app signs people in with {app['DD_OIDC_ISSUER']}.")
    elif not (app.get("DD_PRINCIPAL_ID") and app.get("DD_PRINCIPAL_NAME")):
        app |= EXAMPLE_PRINCIPAL
        print(
            f"No principal is set, so runs act for the example, {EXAMPLE_PRINCIPAL['DD_PRINCIPAL_NAME']}. "
            "Run `uv run scripts/dev.py setup` to give your own."
        )
    if omitted := profile_omissions({**os.environ, **app}):
        print(f"Note: {omissions_note(omitted)}.")
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
            env = base | agent_env(agent)
            if agent.name in MODEL_BACKED and not has_key(env):
                print(
                    f"skip  {agent.script}: no model key "
                    f"(run setup, or set it in {agent.env_file.relative_to(paths.ROOT)})"
                )
                continue
            cmd = ["uv", "run", agent.script, "serve", "--port", str(agent.port)]
            service = Service(agent.name, cmd + (["--reload"] if reload else []), env)
            stack.start(service)
            started.append((agent, service))
        for agent, service in started:
            if stack.wait_for(service, f"{agent.url}/.well-known/agent-card.json"):
                stack.say(
                    agent.name,
                    f"ready at {agent.url}" + (" (reloads as you edit it)" if reload else ""),
                )

        if not agents_only:
            app_service = Service(
                "app",
                ["uv", "run", "data-director"],
                # The app opens a browser on its own address; the page to open is printed below.
                base | app | {"BROWSER": "true"},
            )
            stack.start(app_service)
            if not stack.wait_for(app_service, f"http://127.0.0.1:{APP_PORT}/api/agents"):
                raise DevError("the app did not start; its output is above")
            if web:
                vite = Service(
                    "web",
                    ["npm", "run", "dev"],
                    base | {"DD_APP_URL": f"http://127.0.0.1:{APP_PORT}"},
                    paths.WEB,
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

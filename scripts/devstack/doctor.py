"""`dev.py doctor`: check the toolchain, the settings and the ports; change nothing."""

from __future__ import annotations

import os
import urllib.request
from typing import Any

import yaml

from devstack import paths
from devstack.common import (
    APP_PORT,
    MODEL_BACKED,
    WEB_PORT,
    DevError,
    agent_env,
    answers,
    app_env,
    has_key,
    load_agents,
    needs_build,
    needs_install,
    port_free,
    read_env,
    stray_files,
    tool_problems,
)


def doctor() -> int:
    problems = tool_problems()
    for stray in stray_files():
        problems.append(f"settings file of the old layout, move it: {stray} (ADR-0026)")
    for path in [
        paths.APP_ENV,
        paths.AGENTS_ENV,
        *sorted(paths.AGENT_ENV_DIR.glob("*.env")),
    ]:
        try:
            read_env(path)
        except DevError as exc:
            problems.append(str(exc))
    try:
        env = {**os.environ, **app_env()}
        if not (env.get("DD_PRINCIPAL_ID") and env.get("DD_PRINCIPAL_NAME")):
            print(
                "note: no principal is set; `start` will use the example (run setup to set yours)"
            )
    except DevError as exc:
        problems.append(str(exc))
    for agent in load_agents():
        try:
            keyed = has_key(agent_env(agent) | dict(os.environ))
        except DevError as exc:
            problems.append(str(exc))
            continue
        if agent.name in MODEL_BACKED and not keyed:
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

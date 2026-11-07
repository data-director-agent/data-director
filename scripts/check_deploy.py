"""Check that the VM and the Compose stack run every agent the app lists, on the port it expects.

The app reaches the agents named in `app/config/agents.yaml` (docs/specs/agents.md). On the VM
(deploy/README.md) each one is a systemd instance whose port comes from
`deploy/agents/<name>.env`, which must set the port in the agent's URL.

Which agents the VM starts, and which the app waits for, are not written in the units: `dd.py
apply` generates them from that list and `deployment.yaml` (scripts/ddtool/deployment.py). So the
units in `deploy/systemd/` must name no agent instance, or a list would come back to keep in step.

The development Compose stack (`compose.yaml`) reaches the agents through `docker/agents.yaml`. It
must list the same agents, ports and timeouts as the app's list, each at its service's name, and
`compose.yaml` must start each one on that port.

    uv run python scripts/check_deploy.py

It prints one line per problem and exits 1 if there is any.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "app/config/agents.yaml"
ENV_DIR = ROOT / "deploy/agents"
UNITS = ROOT / "deploy/systemd"
COMPOSE_AGENTS = ROOT / "docker/agents.yaml"
COMPOSE = ROOT / "compose.yaml"

# An agent instance named in a unit, which the units leave to `dd.py apply`. The template
# (`data-director-agent@.service`) is not an instance.
INSTANCE = re.compile(r"data-director-agent@[^.\s]+\.service")


def listed_ports(path: Path = AGENTS) -> dict[str, int | None]:
    """Each agent the app lists, and the port its URL names."""
    agents = yaml.safe_load(path.read_text(encoding="utf-8"))["agents"]
    return {a["name"]: urlsplit(a["url"]).port for a in agents}


def _agents(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["agents"]


def compose_list_problems(app: Path = AGENTS, compose: Path = COMPOSE_AGENTS) -> list[str]:
    """Where `compose`'s list differs from `app`'s in anything but each URL's host, which must be
    the agent's own name (its Compose service)."""
    where = compose.relative_to(ROOT) if compose.is_relative_to(ROOT) else compose
    expected = {a["name"]: a for a in _agents(app)}
    found: list[str] = []
    listed: set[str] = set()
    for agent in _agents(compose):
        name = agent["name"]
        listed.add(name)
        if name not in expected:
            found.append(f"{where}: {name} is not in app/config/agents.yaml")
            continue
        want = expected[name]
        url, want_url = urlsplit(agent["url"]), urlsplit(want["url"])
        if url.hostname != name:
            found.append(f"{where}: {name} is at host {url.hostname}, not its service, {name}")
        if (url.scheme, url.port, url.path) != (want_url.scheme, want_url.port, want_url.path):
            found.append(f"{where}: {name} is at {agent['url']}, agents.yaml says {want['url']}")
        rest = {k: v for k, v in agent.items() if k not in ("name", "url")}
        want_rest = {k: v for k, v in want.items() if k not in ("name", "url")}
        if rest != want_rest:
            found.append(
                f"{where}: {name} has {rest or 'no other settings'}, agents.yaml has {want_rest or 'none'}"
            )
    found += [
        f"{where}: no {name}, which app/config/agents.yaml lists"
        for name in expected
        if name not in listed
    ]
    return found


def compose_service_problems(agents: Path = COMPOSE_AGENTS, compose: Path = COMPOSE) -> list[str]:
    """Where `compose` does not start an agent `agents` lists, on the port and URL it names."""
    services = yaml.safe_load(compose.read_text(encoding="utf-8"))["services"]
    found: list[str] = []
    for agent in _agents(agents):
        name, url = agent["name"], agent["url"]
        port = urlsplit(url).port
        service = services.get(name)
        if service is None:
            found.append(f"compose.yaml: no service {name}, which {agents.name} lists")
            continue
        command = service.get("command", "")
        command = command if isinstance(command, str) else " ".join(command)
        env_port = (service.get("environment") or {}).get("PORT")
        if str(env_port) != str(port) or f"--port {port}" not in command:
            found.append(f"compose.yaml: {name} does not serve on port {port} (PORT and --port)")
        if f"--public-url {url}" not in command:
            found.append(f"compose.yaml: {name} does not give --public-url {url}")
    return found


def env_ports(directory: Path = ENV_DIR) -> dict[str, int | None]:
    """Each deploy/agents/<name>.env, and the PORT it sets (None if it sets none)."""
    ports: dict[str, int | None] = {}
    for env in sorted(directory.glob("*.env")):
        match = re.search(r"^PORT=(\d+)\s*$", env.read_text(encoding="utf-8"), flags=re.M)
        ports[env.stem] = int(match.group(1)) if match else None
    return ports


def named_instances(directory: Path = UNITS) -> list[str]:
    """Each `unit: instance` where a unit in `directory` names an agent instance."""
    return [
        f"{unit.relative_to(directory)}: {found}"
        for unit in sorted(p for p in directory.rglob("*") if p.is_file())
        for line in unit.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
        for found in INSTANCE.findall(line)
    ]


def problems() -> list[str]:
    listed = listed_ports()
    envs = env_ports()
    found: list[str] = []
    for name, port in listed.items():
        if name not in envs:
            found.append(f"{name}: no deploy/agents/{name}.env (PORT={port})")
        elif envs[name] != port:
            found.append(f"deploy/agents/{name}.env: PORT={envs[name]}, agents.yaml says {port}")
    for name in envs.keys() - listed.keys():
        found.append(f"deploy/agents/{name}.env: {name} is not in app/config/agents.yaml")
    found += [
        f"deploy/systemd/{where} is named in a unit; `dd.py apply` generates that list"
        for where in named_instances()
    ]
    found += compose_list_problems()
    found += compose_service_problems()
    return found


def main() -> int:
    found = problems()
    for problem in found:
        print(problem)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())

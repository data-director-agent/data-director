"""Check that the VM deployment runs every agent the app lists, on the port the app expects.

The app reaches the agents named in `app/config/agents.yaml` (docs/specs/agents.md). On the VM
(deploy/README.md) each one is a systemd instance that needs four things to agree with that list:

- `deploy/agents/<name>.env`, whose `PORT` is the port in the agent's URL;
- `Wants=data-director-agent@<name>.service` in `deploy/systemd/data-director.target`;
- `After=` the same unit in `deploy/systemd/data-director-app.service`;
- its port in that unit's `DD_WAIT_PORTS`.

An agent missing from these runs nowhere, and the app lists it as unavailable. An agent that
cannot start without a model key (`NEEDS_KEY`) has its `.env` but is left out of the target and
the app's waits until an operator supplies the key (docs/guide/operations/ai-models.md).

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
TARGET = ROOT / "deploy/systemd/data-director.target"
APP_UNIT = ROOT / "deploy/systemd/data-director-app.service"

# Agents that do not start without a model key, so are not started by default.
NEEDS_KEY = frozenset({"orchestrator-model"})

INSTANCE = re.compile(r"^data-director-agent@(.+)\.service$")


def listed_ports(path: Path = AGENTS) -> dict[str, int]:
    """Each agent the app lists, and the port its URL names."""
    agents = yaml.safe_load(path.read_text(encoding="utf-8"))["agents"]
    return {a["name"]: urlsplit(a["url"]).port for a in agents}


def env_ports(directory: Path = ENV_DIR) -> dict[str, int | None]:
    """Each deploy/agents/<name>.env, and the PORT it sets (None if it sets none)."""
    ports: dict[str, int | None] = {}
    for env in sorted(directory.glob("*.env")):
        match = re.search(r"^PORT=(\d+)\s*$", env.read_text(encoding="utf-8"), flags=re.M)
        ports[env.stem] = int(match.group(1)) if match else None
    return ports


def unit_values(path: Path, key: str) -> list[str]:
    """Every value of `key=` in a unit file, space-separated values split, in order."""
    values: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            values.extend(line.split("=", 1)[1].split())
    return values


def instances(units: list[str]) -> list[str]:
    """The agent names of the data-director-agent@ instances among `units`."""
    return [m.group(1) for u in units if (m := INSTANCE.match(u))]


def wait_ports(path: Path = APP_UNIT) -> list[int]:
    """The ports in the app unit's DD_WAIT_PORTS."""
    text = path.read_text(encoding="utf-8")
    match = re.search(r'^Environment="?DD_WAIT_PORTS=([\d ]*)"?\s*$', text, flags=re.M)
    return [int(p) for p in match.group(1).split()] if match else []


def problems() -> list[str]:
    listed = listed_ports()
    envs = env_ports()
    started = {name for name in listed if name not in NEEDS_KEY}
    found: list[str] = []

    for name, port in listed.items():
        if name not in envs:
            found.append(f"{name}: no deploy/agents/{name}.env (PORT={port})")
        elif envs[name] != port:
            found.append(f"deploy/agents/{name}.env: PORT={envs[name]}, agents.yaml says {port}")
    for name in envs.keys() - listed.keys():
        found.append(f"deploy/agents/{name}.env: {name} is not in app/config/agents.yaml")

    for path, key in ((TARGET, "Wants"), (APP_UNIT, "After")):
        named = set(instances(unit_values(path, key)))
        where = f"{path.relative_to(ROOT)} {key}="
        found += [
            f"{where}: missing data-director-agent@{n}.service" for n in sorted(started - named)
        ]
        found += [
            f"{where}: data-director-agent@{n}.service is not started by default"
            for n in sorted(named - started)
        ]

    waits = wait_ports()
    expected = {listed[n] for n in started}
    found += [f"DD_WAIT_PORTS: missing {p}" for p in sorted(expected - set(waits))]
    found += [
        f"DD_WAIT_PORTS: {p} is no started agent's port" for p in sorted(set(waits) - expected)
    ]
    return found


def main() -> int:
    found = problems()
    for problem in found:
        print(problem)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())

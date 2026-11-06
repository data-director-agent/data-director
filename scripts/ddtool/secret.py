"""`dd.py secret set|remove|list`: give an agent a secret, such as its model key, take it away, or
list them.

On a VM this is deploy/secret.sh, run from the clone: the secret becomes a systemd credential of
that agent's unit alone (deploy/README.md, "Secrets"). In development the secret is a file in
`config/local/credentials/`, named by `<SECRET>_FILE` in the agent's own settings, which is how
`dd_sdk.credentials` finds it in both places.
"""

from __future__ import annotations

import getpass
import os
import re
import sys
from pathlib import Path

from ddtool import paths
from ddtool.common import DevError, load_agents, read_env, shown, update_env
from ddtool.vm import Vm

SECRET_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
HEADER = "# This agent's own settings (docs/specs/policy-and-identity.md)."


def variable(secret: str) -> str:
    """The variable an agent reads a secret's file name from (anthropic-api-key ->
    ANTHROPIC_API_KEY_FILE), as deploy/credentials.sh names it."""
    return f"{secret.upper().replace('-', '_')}_FILE"


def secret_file(agent: str, secret: str) -> Path:
    """Where development keeps an agent's secret."""
    return paths.CREDENTIALS_DIR / f"{agent}-{secret}"


def _check(agent: str, secret: str) -> None:
    names = {a.name for a in load_agents()}
    if agent not in names:
        raise DevError(f"no agent {agent!r} in app/config/agents.yaml")
    if not SECRET_NAME.match(secret):
        raise DevError(f"{secret!r}: a secret's name is lower-case words joined by hyphens")


def _value(agent: str, secret: str) -> str:
    if sys.stdin.isatty():
        value = getpass.getpass(f"Value for {secret} of {agent} (not shown): ")
    else:
        value = sys.stdin.read()
    value = value.strip()
    if not value or "\n" in value:
        raise DevError("give one line, not empty")
    return value


def dev_set(agent: str, secret: str, value: str | None = None) -> None:
    _check(agent, secret)
    value = _value(agent, secret) if value is None else value
    path = secret_file(agent, secret)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.touch(mode=0o600)
    path.chmod(0o600)
    path.write_text(value + "\n", encoding="utf-8")
    update_env(paths.AGENT_ENV_DIR / f"{agent}.env", {variable(secret): path.name}, HEADER)
    print(f"stored {shown(path)}, named by {variable(secret)} in {agent}'s settings")


def dev_remove(agent: str, secret: str) -> None:
    _check(agent, secret)
    path = secret_file(agent, secret)
    if not path.exists():
        raise DevError(f"{shown(path)} does not exist")
    path.unlink()
    env_file = paths.AGENT_ENV_DIR / f"{agent}.env"
    if env_file.is_file():
        kept = [
            line
            for line in env_file.read_text(encoding="utf-8").splitlines()
            if line.strip().removeprefix("export ").partition("=")[0].strip() != variable(secret)
        ]
        env_file.write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"removed {shown(path)}")


def dev_list() -> None:
    found = False
    for agent in load_agents():
        for name, value in read_env(agent.env_file).items():
            if not name.endswith("_FILE"):
                continue
            found = True
            path = paths.CREDENTIALS_DIR / value
            state = "ok" if path.is_file() and path.stat().st_size else "PROBLEM: missing or empty"
            print(f"{agent.name:22} {name:30} {shown(path)}  {state}")
    if not found:
        print(f"no agent names a secret in {shown(paths.AGENT_ENV_DIR)}")


def secret(target: str, args: list[str], vm: Vm | None = None) -> int:
    if target == "vm":
        script = (vm or Vm()).clone / "deploy" / "secret.sh"
        os.execvp("bash", ["bash", str(script), *args])
    match args:
        case ["set", agent, name]:
            dev_set(agent, name)
        case ["remove", agent, name]:
            dev_remove(agent, name)
        case ["list"]:
            dev_list()
        case _:
            raise DevError("usage: secret set AGENT SECRET | remove AGENT SECRET | list")
    return 0

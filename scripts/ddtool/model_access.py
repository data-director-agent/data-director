"""Whether an agent on a VM has the model credentials it starts with: a provider key, or, when it
calls through the model broker, its broker credential and no provider key
(dd_sdk.credentials.model_endpoint, docs/guide/operations/model-broker.md). `dd.py doctor` and
`dd.py apply` both ask, so each says the same of an agent the broker serves."""

from __future__ import annotations

from dataclasses import dataclass

from ddtool.common import PROVIDER_KEYS
from ddtool.vm import System, Vm, loaded_secrets, read_settings

BROKER_URL = "DD_MODEL_BROKER_URL"
BROKER_SECRET = "dd-model-broker-credential"
BROKER_CREDENTIAL = "DD_MODEL_BROKER_CREDENTIAL"
BROKER_SCRIPT = "sudo deploy/broker-credentials.sh"


def secret_name(variable: str) -> str:
    """The secret whose file deploy/credentials.sh names in `variable`'s `_FILE` form
    (ANTHROPIC_API_KEY -> anthropic-api-key)."""
    return variable.lower().replace("_", "-")


@dataclass(frozen=True)
class ModelAccess:
    """What an agent's settings and secrets give it: `brokered` if it calls through the broker,
    `credential` if its broker credential is in place, `key` if its provider's key is, and
    `secret`, the name of the secret that key is given as."""

    brokered: bool
    credential: bool
    key: bool
    secret: str

    def broker_problem(self, name: str, tool: str) -> tuple[str, str] | None:
        """Why an agent that calls through the broker stops at start-up, and the fix; None if it
        does not call through the broker or would start."""
        if not self.brokered:
            return None
        if self.key:
            return (
                f"{name} calls through the model broker ({BROKER_URL}) but also holds a provider "
                "key, so it stops at start-up",
                f"{tool} secret remove {name} {self.secret}",
            )
        if not self.credential:
            return (
                f"{name} calls through the model broker ({BROKER_URL}) but has no broker "
                f"credential ({BROKER_SECRET})",
                f"{BROKER_SCRIPT} <every agent that calls through the broker>",
            )
        return None


def _stored(system: System, vm: Vm, name: str, secret: str) -> bool:
    """Whether agent `name` has `secret`: its file, which only root can see, or else the line in
    its credentials drop-in that loads it."""
    if system.is_root():
        stored = vm.credentials / name / secret
        return stored.is_file() and stored.stat().st_size > 0
    return secret in loaded_secrets(system, vm, name)


def vm_model_access(system: System, vm: Vm, name: str) -> ModelAccess:
    """`name`'s model access on a VM, from agents.env and its own settings, which win, as its unit
    reads them, and from its secrets. A file this user may not read counts as empty."""
    env = (read_settings(system, vm.agents_env) or {}) | (
        read_settings(system, vm.agent_env(name)) or {}
    )
    provider = env.get("DD_MODEL_PROVIDER") or "anthropic"
    variable = PROVIDER_KEYS.get(provider, PROVIDER_KEYS["anthropic"])
    secret = secret_name(variable)
    key = bool(
        env.get(variable) or env.get(f"{variable}_FILE") or _stored(system, vm, name, secret)
    )
    credential = bool(
        env.get(BROKER_CREDENTIAL)
        or env.get(f"{BROKER_CREDENTIAL}_FILE")
        or _stored(system, vm, name, BROKER_SECRET)
    )
    return ModelAccess(bool((env.get(BROKER_URL) or "").strip()), credential, key, secret)

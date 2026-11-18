"""Whether an agent on a VM has the model credentials it starts with: a provider key, or, when it
calls through the model broker, its broker credential and no provider key
(dd_sdk.credentials.model_endpoint, docs/guide/operations/model-broker.md). `dd.py doctor` and
`dd.py apply` both ask, so each says the same of an agent the broker serves."""

from __future__ import annotations

from dataclasses import dataclass

from ddtool.common import PROVIDER_KEYS, shown
from ddtool.vm import System, Vm, loaded_secrets, read_settings

BROKER_URL = "DD_MODEL_BROKER_URL"
BROKER_FILE = "dd-model-broker-credential"
BROKER_CREDENTIAL = "DD_MODEL_BROKER_CREDENTIAL"
BROKER_SCRIPT = "sudo deploy/broker-credentials.sh"


def file_label(variable: str) -> str:
    """The name under credentials/<agent>/ that deploy/credentials.sh gives `variable` in its
    `_FILE` form (ANTHROPIC_API_KEY -> anthropic-api-key). It names a file, never holds a value."""
    return variable.lower().replace("_", "-")


@dataclass(frozen=True)
class ModelAccess:
    """What an agent's settings and secrets give it: `brokered` if it calls through the broker,
    `credential` if its broker credential is in place, `key` if its provider's key is, and
    `provider_file`, the file name that key is given under."""

    brokered: bool
    credential: bool
    key: bool
    provider_file: str

    def broker_problem(self, name: str, tool: str) -> tuple[str, str] | None:
        """Why an agent that calls through the broker stops at start-up, and the fix; None if it
        does not call through the broker or would start."""
        if not self.brokered:
            return None
        if self.key:
            return (
                f"{name} calls through the model broker ({BROKER_URL}) but also holds a provider "
                "key, so it stops at start-up",
                f"{tool} secret remove {name} {self.provider_file}",
            )
        if not self.credential:
            return (
                f"{name} calls through the model broker ({BROKER_URL}) but has no broker "
                f"credential ({BROKER_FILE})",
                f"{BROKER_SCRIPT} <every agent that calls through the broker>",
            )
        return None


def _stored(system: System, vm: Vm, name: str, label: str) -> bool:
    """Whether agent `name` has the file `label`: its file, which only root can see, or else the line in
    its credentials drop-in that loads it."""
    if system.is_root():
        stored = vm.credentials / name / label
        return stored.is_file() and stored.stat().st_size > 0
    return label in loaded_secrets(system, vm, name)


def vm_model_access(system: System, vm: Vm, name: str) -> ModelAccess:
    """`name`'s model access on a VM, from agents.env and its own settings, which win, as its unit
    reads them, and from its secrets. A file this user may not read counts as empty."""
    env = (read_settings(system, vm.agents_env) or {}) | (
        read_settings(system, vm.agent_env(name)) or {}
    )
    provider = env.get("DD_MODEL_PROVIDER") or "anthropic"
    variable = PROVIDER_KEYS.get(provider, PROVIDER_KEYS["anthropic"])
    label = file_label(variable)
    key = bool(env.get(variable) or env.get(f"{variable}_FILE") or _stored(system, vm, name, label))
    credential = bool(
        env.get(BROKER_CREDENTIAL)
        or env.get(f"{BROKER_CREDENTIAL}_FILE")
        or _stored(system, vm, name, BROKER_FILE)
    )
    return ModelAccess(bool((env.get(BROKER_URL) or "").strip()), credential, key, label)


# The secrets in credentials/app/ that the harness signs model grants with, which
# deploy/credentials.sh loads into the app's model-grants.conf (docs/guide/operations/model-broker.md).
APP_MODEL_GRANT_SECRETS = (
    "model-grant-signing-key",
    "model-broker-subject-key",
    "pseudonym-secret",
)


def app_model_grants_pending(system: System, vm: Vm) -> str | None:
    """The app's model-grant drop-in, if it does not load exactly the secrets in place. Only root
    can see the secrets, so for anyone else this is None."""
    if not system.is_root():
        return None
    dropin = vm.unit_dir / "data-director-app.service.d" / "model-grants.conf"
    present = {n for n in APP_MODEL_GRANT_SECRETS if system.exists(vm.credentials / "app" / n)}
    text = system.read(dropin) if system.readable(dropin) else ""
    loaded = {n for n in APP_MODEL_GRANT_SECRETS if f"LoadCredential={n}:" in text}
    return shown(dropin) if present != loaded else None

"""The app's agent list as `dd.py apply` writes it, and which agents call through the model broker.

The release's `app/config/agents.yaml` says where each agent is. Whether an agent calls its models
through the model broker is the operator's statement, made by setting `DD_MODEL_BROKER_URL` in its
settings or in `agents.env`. `apply` writes the release's list beside `deployment.yaml` with
`model_broker: true` on each such agent and names it with `DD_AGENTS_CONFIG` in `app.env`, since the
harness reads that statement from the list alone and refuses a model-backed agent without it while
people's own model accounts may pay (docs/specs/model-accounts.md, invariant 14).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from ddtool import paths
from ddtool.common import MODEL_BACKED, Agent, has_key, model_on_by_default, read_env
from ddtool.model_access import BROKER_URL, vm_model_access
from ddtool.vm import System, Vm, read_settings

AGENTS_CONFIG_VARIABLE = "DD_AGENTS_CONFIG"
FILE_NAME = "agents.yaml"
# The harness's statement, in each entry (dd_harness.registry).
MARK = "model_broker"
# The settings of `model_accounts.own` under which the harness refuses an unmarked agent.
OWN_ACCOUNTS_ON = ("allowed", "required")


def agent_list(release_list: Path, brokered: Iterable[str], header: str) -> str:
    """The release's agent list with `model_broker: true` on each entry named in `brokered` and on
    no other, in the release's order, under `header`."""
    data: dict[str, Any] = yaml.safe_load(release_list.read_text(encoding="utf-8")) or {}
    marked = set(brokered)
    entries = []
    for entry in data.get("agents") or []:
        kept = {key: value for key, value in dict(entry).items() if key != MARK}
        if kept.get("name") in marked:
            kept[MARK] = True
        entries.append(kept)
    body = {**data, "agents": entries}
    return f"{header}\n" + yaml.safe_dump(body, sort_keys=False, allow_unicode=True)


def brokered_on_vm(system: System, vm: Vm, names: Iterable[str]) -> set[str]:
    """Those of `names` whose settings on the VM say they call through the model broker."""
    return {name for name in names if vm_model_access(system, vm, name).brokered}


def brokered_locally(names: Iterable[str]) -> set[str]:
    """Those of `names` whose settings in `config/local/` say they call through the model broker,
    from `agents.env` and their own file, which wins, as `dd.py start` gives them."""
    shared = read_env(paths.AGENTS_ENV)
    return {
        name
        for name in names
        if ((shared | read_env(paths.AGENT_ENV_DIR / f"{name}.env")).get(BROKER_URL) or "").strip()
    }


def own_accounts_on(model_accounts: dict[str, Any] | None) -> bool:
    """Whether `model_accounts`, as `deployment.yaml` gives it, lets people's own accounts pay."""
    own = (model_accounts or {}).get("own")
    return str(own or "off") in OWN_ACCOUNTS_ON


def broker_refusals(
    system: System,
    vm: Vm | None,
    model_accounts: dict[str, Any] | None,
    running: Iterable[Agent],
    brokered: set[str],
) -> list[str]:
    """Why `apply` will not run each agent that calls a model without the model broker while
    `model_accounts` lets people's own accounts pay: the app would refuse every run of it. `vm` is
    None in development, where a model on by default runs only with a key (`dd.py start`)."""
    if not own_accounts_on(model_accounts):
        return []
    refusals = []
    for agent in running:
        if agent.name in brokered:
            continue
        if vm is None:
            settings = paths.AGENT_ENV_DIR / f"{agent.name}.env"
            env = read_env(paths.AGENTS_ENV) | read_env(settings)
            model_on = model_on_by_default(agent.name, env) and has_key(env)
        else:
            settings = vm.agent_env(agent.name)
            model_on = model_on_by_default(agent.name, read_settings(system, settings) or {})
        if agent.name in MODEL_BACKED or model_on:
            refusals.append(
                f"{agent.name} calls a model without the model broker while model_accounts lets "
                "people's own accounts pay, so the app would refuse its runs; first: set "
                f"{BROKER_URL} in {settings} and give it its broker credential "
                "(docs/guide/operations/model-broker.md), or turn model_accounts off"
            )
    return refusals

"""`dd.py apply` writes the app's agent list, marking each agent that calls through the model
broker, and refuses own model accounts for an agent that does not (scripts/ddtool/agent_list.py,
docs/specs/model-accounts.md, invariant 14)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ddtool.common import read_env  # noqa: E402
from ddtool.deployment import Place, apply  # noqa: E402
from ddtool.vm import Vm  # noqa: E402
from test_vm_doctor import (  # noqa: E402  # the VM under tmp_path and its stand-ins
    AGENTS,
    BROKERED,
    SHA,
    FakeVm,
    check,
    model_orchestrator,
    says,
    vm,
)

__all__ = ["vm"]  # the fixture, used by name

OWN_ACCOUNTS = "model_accounts:\n  own: allowed\n"


def entries(vm: Vm) -> dict[str, dict[str, Any]]:
    """The agent list `apply` wrote, by name."""
    listed = yaml.safe_load((vm.etc / "agents.yaml").read_text())["agents"]
    return {entry["name"]: entry for entry in listed}


def test_apply_writes_the_release_list_and_names_it_in_app_env(vm: Vm) -> None:
    release = {e["name"]: e for e in yaml.safe_load(AGENTS)["agents"]}
    written = entries(vm)
    assert {name: entry["url"] for name, entry in written.items()} == {
        name: entry["url"] for name, entry in release.items()
    }
    assert not any("model_broker" in entry for entry in written.values())
    assert read_env(vm.app_env)["DD_AGENTS_CONFIG"] == str(vm.etc / "agents.yaml")


@pytest.mark.parametrize("shared", [False, True])
def test_an_agent_that_calls_through_the_broker_is_marked(vm: Vm, shared: bool) -> None:
    system = model_orchestrator(vm, "" if shared else BROKERED, "dd-model-broker-credential")
    if shared:
        vm.agents_env.write_text(BROKERED)
    assert apply(system, Place.vm(vm), vm) == 0
    written = entries(vm)
    assert written["orchestrator-model"]["model_broker"] is True
    # The shared settings are every agent's; the harness asks only of agents that call a model.
    assert ("model_broker" in written["orchestrator-stub"]) is shared


def test_apply_again_changes_nothing(vm: Vm, capsys: pytest.CaptureFixture[str]) -> None:
    system = model_orchestrator(vm, BROKERED, "dd-model-broker-credential")
    assert apply(system, Place.vm(vm), vm) == 0
    capsys.readouterr()
    assert apply(system, Place.vm(vm), vm, check=True) == 0
    assert "Nothing to change." in capsys.readouterr().out


def own_accounts(vm: Vm) -> None:
    deployment = vm.etc / "deployment.yaml"
    deployment.write_text(deployment.read_text() + OWN_ACCOUNTS)


def test_own_accounts_refuse_a_model_agent_with_its_own_key(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    system = model_orchestrator(vm, "", "anthropic-api-key")
    own_accounts(vm)
    before = (vm.etc / "profile.yaml").read_text()
    assert apply(system, Place.vm(vm), vm) == 1
    assert says(capsys.readouterr().out, "refused", "orchestrator-model", "DD_MODEL_BROKER_URL")
    assert (vm.etc / "profile.yaml").read_text() == before  # nothing written
    status, out = check(system, vm, capsys)
    assert status == 1
    assert says(out, "problem", "orchestrator-model", "DD_MODEL_BROKER_URL")


def test_own_accounts_with_a_brokered_model_agent_apply(vm: Vm) -> None:
    system = model_orchestrator(vm, BROKERED, "dd-model-broker-credential")
    own_accounts(vm)
    assert apply(system, Place.vm(vm), vm) == 0
    assert entries(vm)["orchestrator-model"]["model_broker"] is True


def test_a_model_agent_with_its_own_key_applies_while_the_deployment_pays(vm: Vm) -> None:
    system = model_orchestrator(vm, "", "anthropic-api-key")
    assert apply(system, Place.vm(vm), vm) == 0
    assert "model_broker" not in entries(vm)["orchestrator-model"]


def test_doctor_reports_a_list_the_live_release_has_moved_past(
    vm: Vm, capsys: pytest.CaptureFixture[str]
) -> None:
    release_list: Path = vm.releases / SHA / "app" / "config" / "agents.yaml"
    release_list.write_text(AGENTS.replace(":8101/", ":8199/"))  # a deploy moved a port
    status, out = check(FakeVm(), vm, capsys)
    assert status == 1
    assert says(out, "problem", "agents.yaml")
    assert says(out, "fix", "apply")

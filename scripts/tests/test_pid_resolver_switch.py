"""`pid_resolver: true` in deployment.yaml: `apply` grants the Linking Adviser the PID resolver's
servers and names their list in app.env, `start` runs the server, and a VM refuses it for now
(scripts/ddtool/deployment.py, scripts/ddtool/start.py, mcp-pid/README.md)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ddtool.common import DevError, load_agents  # noqa: E402
from ddtool.deployment import Place, parse, plan, profile  # noqa: E402
from ddtool.pid_resolver import (  # noqa: E402
    TOOLS_CONFIG_VARIABLE,
    server_env,
    settings,
    tool_servers,
)
from ddtool.vm import Vm  # noqa: E402
from test_vm_doctor import FakeVm, vm  # noqa: E402  # the VM under tmp_path and its stand-ins

from dd_harness.gateway.config import load_servers, tools_digest  # noqa: E402
from dd_harness.policy import load_profile  # noqa: E402
from dd_mcp_pid.cli import registries  # noqa: E402

__all__ = ["vm"]  # the fixture, used by name

AGENTS = load_agents(ROOT / "app" / "config" / "agents.yaml")
EXAMPLE = ROOT / "app" / "config" / "profile.yaml.example"
TOOLS = ROOT / "app" / "config" / "tools.yaml"


def generated(text: str, tmp_path: Path) -> Path:
    deployment = parse(text, "deployment.yaml", AGENTS)
    pid = settings(
        on=deployment.pid_resolver, disabled=deployment.disabled, source=ROOT, on_vm=False
    )
    path = tmp_path / "profile.yaml"
    path.write_text(profile(deployment, EXAMPLE, None, pid.tool_servers))
    return path


def test_the_switch_is_off_unless_set_and_must_be_a_boolean() -> None:
    assert parse("name: dev\n", "deployment.yaml", AGENTS).pid_resolver is False
    assert parse("name: dev\npid_resolver: true\n", "deployment.yaml", AGENTS).pid_resolver
    with pytest.raises(DevError, match="pid_resolver is true or false"):
        parse("name: dev\npid_resolver: yes please\n", "deployment.yaml", AGENTS)


def test_on_it_grants_the_linking_adviser_every_server_the_tools_config_lists(
    tmp_path: Path,
) -> None:
    path = generated("name: dev\npid_resolver: true\n", tmp_path)
    servers = tool_servers(TOOLS)
    assert servers == [s.name for s in load_servers(TOOLS)]
    assert yaml.safe_load(path.read_text())["tool_servers"] == {"advisor.linking": servers}
    assert load_profile(path).tool_servers == {"advisor.linking": tuple(servers)}


@pytest.mark.parametrize(
    "text", ["name: dev\n", "name: dev\npid_resolver: true\ndisabled: [advisor-linking]\n"]
)
def test_off_or_without_the_linking_adviser_nothing_is_granted(text: str, tmp_path: Path) -> None:
    assert "tool_servers" not in yaml.safe_load(generated(text, tmp_path).read_text())


def test_apply_names_the_tools_config_in_app_env_only_when_it_is_on(tmp_path: Path) -> None:
    place = Place(tmp_path / "local", ROOT)
    place.etc.mkdir()
    place.deployment.write_text("name: dev\npid_resolver: true\n")
    _, on = plan(FakeVm(), place)
    assert on.app_env is not None and on.app_env[1][TOOLS_CONFIG_VARIABLE] == str(TOOLS)
    place.deployment.write_text("name: dev\n")
    _, off = plan(FakeVm(), place)
    assert off.app_env is not None and off.app_env[1][TOOLS_CONFIG_VARIABLE] is None


def test_a_vm_refuses_it_until_the_server_has_a_unit(vm: Vm) -> None:
    (vm.etc / "deployment.yaml").write_text("name: test\npid_resolver: true\n")
    _, result = plan(FakeVm(), Place.vm(vm), vm)
    assert any("pid_resolver is for development only" in r for r in result.refusals)


def test_start_gives_the_server_the_pinned_registries() -> None:
    env = server_env()
    assert env["DD_PID_ROR_REGISTRY"].endswith("agents/advisor-policy/data/ror/registry.jsonl")
    assert env["DD_PID_ROR_SNAPSHOT"].startswith("ROR dump v")
    assert env["DD_PID_JOURNALS_REGISTRY"].endswith("journals/src/dd_journals/data/journals.sqlite")


@pytest.mark.parametrize("config", [TOOLS, ROOT / "docker" / "tools.yaml"], ids=["app", "docker"])
def test_each_tools_config_pins_the_tools_the_server_lists(config: Path) -> None:
    servers = {s.name: s for s in load_servers(config)}
    assert list(servers) == ["datacite", "crossref", "orcid", "ror", "journals"]
    for registry in registries({}):
        listed = [
            t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in registry.tools
        ]
        assert tools_digest(listed) == servers[registry.name].tools_sha256, (
            f"{registry.name}'s tools changed: review them, then update both tools.yaml pins"
        )
        assert servers[registry.name].url.endswith(f":8310/{registry.name}/mcp")

"""Agent discovery (ADR-0010): entry points, the manifest, and the `agents` command."""

from __future__ import annotations

import json

import pytest

from tests.fakes import ScriptedAgent, review_of_input
from workbench.agents.base import Agent, describe
from workbench.agents.registry import Registry, RegistryError
from workbench.cli import main
from workbench.contract.models import GroundingMode
from workbench.settings import Settings, build_registry

IN_TREE = {"fact.checker", "hello.world", "quality.reviewer", "stub.abstain"}


@pytest.mark.requirement("DD-REGISTRY")
def test_entry_points_load_every_in_tree_agent_and_record_the_unported_one() -> None:
    registry = build_registry(Settings())
    assert set(registry.ids()) == IN_TREE, "run `uv sync` after adding an entry point"
    assert "r3" in registry.unavailable and "TODO" in registry.unavailable["r3"]
    for agent in registry:
        assert isinstance(agent, Agent)


@pytest.mark.requirement("DD-REGISTRY")
def test_manifest_describes_each_agent_from_one_source() -> None:
    registry = build_registry(Settings())
    manifest = {m["agent_id"]: m for m in registry.manifest()}
    assert set(manifest) == IN_TREE
    for agent_id, entry in manifest.items():
        spec = registry.agents[agent_id].spec
        assert entry == describe(spec)
        assert set(entry) == {
            "agent_id",
            "version",
            "description",
            "requirement_ids",
            "action_class",
            "accepts",
            "grounding_mode",
            "payload",
            "uischema",
        }
        assert entry["grounding_mode"] in {m.value for m in GroundingMode}
        assert entry["accepts"], "an agent must accept at least one input class"
        json.dumps(entry)  # JSON-ready


def test_duplicate_agent_id_is_a_registry_error() -> None:
    a = ScriptedAgent(GroundingMode.NONE, review_of_input)
    b = ScriptedAgent(GroundingMode.NONE, review_of_input)
    with pytest.raises(RegistryError, match="two agents"):
        Registry.from_agents([a, b])


def test_object_without_the_protocol_is_a_registry_error() -> None:
    with pytest.raises(RegistryError, match="Agent protocol"):
        Registry.from_agents([object()])  # type: ignore[list-item]


@pytest.mark.requirement("DD-REGISTRY")
def test_agents_command_lists_the_registry(capsys) -> None:
    assert main(["agents"]) == 0
    out = capsys.readouterr().out
    for agent_id in IN_TREE:
        assert agent_id in out
    assert "input_only" in out and "[r3] unavailable" in out
    assert main(["agents", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {m["agent_id"] for m in data["agents"]} == IN_TREE and "r3" in data["unavailable"]

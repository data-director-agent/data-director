"""`apply` writes the release's profile example with the keys it sets itself, and carries every
other key as the example has it (scripts/ddtool/deployment.py, docs/guide/operations/configuration.md)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ddtool.common import load_agents  # noqa: E402
from ddtool.deployment import OWNED_PROFILE_KEYS, parse, profile  # noqa: E402

from dd_harness.policy import PROFILE_KEYS, load_profile  # noqa: E402

AGENTS = load_agents(ROOT / "app" / "config" / "agents.yaml")
EXAMPLE = ROOT / "app" / "config" / "profile.yaml.example"


def generated(
    tmp_path: Path, text: str = "name: dev\n", example: Path = EXAMPLE, current: str | None = None
) -> tuple[Path, dict[str, Any]]:
    deployment = parse(text, "deployment.yaml", AGENTS)
    path = tmp_path / "profile.yaml"
    path.write_text(profile(deployment, example, current))
    return path, yaml.safe_load(path.read_text())


def example_with(tmp_path: Path, extra: dict[str, Any]) -> Path:
    """The release's example with `extra` keys added."""
    body = {**yaml.safe_load(EXAMPLE.read_text()), **extra}
    path = tmp_path / "example.yaml"
    path.write_text(yaml.safe_dump(body, sort_keys=False))
    return path


def test_the_example_keys_apply_does_not_set_reach_the_profile(tmp_path: Path) -> None:
    path, made = generated(tmp_path)
    example = yaml.safe_load(EXAMPLE.read_text())
    carried = set(example) - OWNED_PROFILE_KEYS
    assert "deposit_transports" in carried
    assert {key: made[key] for key in carried} == {key: example[key] for key in carried}
    assert load_profile(path).deposit_transports == load_profile(EXAMPLE).deposit_transports


def test_every_key_the_loader_knows_is_carried_or_set_by_apply() -> None:
    assert OWNED_PROFILE_KEYS <= PROFILE_KEYS


def test_keys_a_later_example_adds_are_carried(tmp_path: Path) -> None:
    example = example_with(
        tmp_path,
        {
            "attached_documents": "refused",
            "remote_tool_content": ["inventory"],
            "model_footprint": {
                "source": "test",
                "as_of": date(2026, 1, 1),
                "models": {},
            },
        },
    )
    path, made = generated(tmp_path, example=example)
    assert made["attached_documents"] == "refused"
    assert made["remote_tool_content"] == ["inventory"]
    assert made["model_footprint"] == {"source": "test", "as_of": date(2026, 1, 1), "models": {}}
    assert load_profile(path).attached_documents == "refused"


def test_agent_settings_of_a_disabled_agent_are_left_out(tmp_path: Path) -> None:
    example = example_with(
        tmp_path,
        {"agent_settings": {"advisor.policy": {"depth": "2"}, "advisor.repository": {"n": "1"}}},
    )
    path, made = generated(tmp_path, "name: dev\ndisabled: [advisor-policy]\n", example)
    assert made["agent_settings"] == {"advisor.repository": {"n": "1"}}
    assert "advisor.policy" not in made["agents"]
    assert load_profile(path).agent_settings == {"advisor.repository": {"n": "1"}}


def test_model_accounts_and_tool_servers_are_not_taken_from_the_example(tmp_path: Path) -> None:
    example = example_with(tmp_path, {"tool_servers": {"advisor.policy": ["x"]}})
    _, made = generated(tmp_path, example=example)
    assert "tool_servers" not in made
    assert yaml.safe_load(EXAMPLE.read_text())["model_accounts"] and "model_accounts" not in made
    _, made = generated(tmp_path, "name: dev\nmodel_accounts:\n  own: allowed\n")
    assert made["model_accounts"] == {"own": "allowed"}


def test_applying_again_keeps_the_version(tmp_path: Path) -> None:
    path, first = generated(tmp_path)
    _, second = generated(tmp_path, current=path.read_text())
    assert second == first

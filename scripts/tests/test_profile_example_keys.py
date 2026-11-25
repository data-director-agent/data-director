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


def test_the_institutions_repositories_are_the_deployments_own(tmp_path: Path) -> None:
    """`institution_repositories` names the instance's own institution's repositories, so it is
    taken from deployment.yaml, as written, and never from the release's example."""
    entry = {"repository_id": "r3d100012124", "charges_deposit_fee": False}
    example = example_with(tmp_path, {"institution_repositories": [{"repository_id": "bl.york"}]})
    _, without = generated(tmp_path, example=example)
    assert "institution_repositories" not in without
    text = yaml.safe_dump({"name": "dev", "institution_repositories": [entry]})
    path, body = generated(tmp_path, text, example=example)
    assert body["institution_repositories"] == [entry]
    (loaded,) = load_profile(path).institution_repositories
    assert loaded.repository_id == "r3d100012124"


def test_the_institutions_storage_is_the_deployments_own(tmp_path: Path) -> None:
    """`institution_storage` names the instance's own institution's storage, so it is taken from
    deployment.yaml, as written, and never from the release's example."""
    entry = {"storage_id": "research-filestore", "storage_name": "Research filestore"}
    example = example_with(tmp_path, {"institution_storage": [{**entry, "storage_id": "other"}]})
    _, without = generated(tmp_path, example=example)
    assert "institution_storage" not in without
    text = yaml.safe_dump({"name": "dev", "institution_storage": [entry]})
    path, body = generated(tmp_path, text, example=example)
    assert body["institution_storage"] == [entry]
    (loaded,) = load_profile(path).institution_storage
    assert loaded.storage_id == "research-filestore"


def test_the_example_deployments_storage_reaches_a_profile_that_loads(tmp_path: Path) -> None:
    """The example `deployment.yaml` names storage live, so a new instance's generated profile
    holds it and the harness loads it."""
    text = (ROOT / "config" / "examples" / "deployment.yaml").read_text()
    path, body = generated(tmp_path, text)
    assert body["institution_storage"] == yaml.safe_load(text)["institution_storage"]
    held = load_profile(path).institution_storage
    assert held
    assert {s.approved_for_sensitive for s in held} == {True, False}


def test_the_administrators_and_steward_teams_are_the_deployments_own(tmp_path: Path) -> None:
    """Deployment roles are the instance's own (docs/specs/stewardship.md, invariant 1), so they
    are taken from deployment.yaml, as written, and never from the release's example."""
    admin = "https://orcid.org/0000-0002-1825-0097"
    team = {"id": "library-rdm", "name": "Library Research Data Team", "members": [admin]}
    example = example_with(tmp_path, {"administrators": ["https://orcid.org/0000-0001-5000-0007"]})
    _, without = generated(tmp_path, example=example)
    assert "administrators" not in without and "stewardship" not in without
    text = yaml.safe_dump(
        {"name": "dev", "administrators": [admin], "stewardship": {"teams": [team]}}
    )
    path, body = generated(tmp_path, text, example=example)
    assert body["administrators"] == [admin]
    assert body["stewardship"] == {"teams": [team]}
    loaded = load_profile(path)
    assert loaded.roles_of(admin).administrator and loaded.roles_of(admin).steward


def test_a_deployment_is_closed_unless_its_deployment_file_opens_it(tmp_path: Path) -> None:
    """docs/specs/policy-and-identity.md, Admission: a deployment admits only whom it lists, its
    stewards and administrators, unless deployment.yaml says otherwise; access is its own."""
    ada = "https://orcid.org/0000-0001-5000-0007"
    josiah = "https://orcid.org/0000-0002-1825-0097"
    example = example_with(tmp_path, {"access": {"admit": "anyone"}})
    path, closed = generated(tmp_path, example=example)
    assert closed["access"] == {"admit": "listed"}
    assert not load_profile(path).admits(ada)

    text = yaml.safe_dump({"name": "dev", "access": {"admit": "anyone", "block": [ada]}})
    path, opened = generated(tmp_path, text, example=example)
    assert opened["access"] == {"admit": "anyone", "block": [ada]}
    loaded = load_profile(path)
    assert loaded.admits(josiah) and not loaded.admits(ada)

"""Agent discovery (ADR-0011): agents.yaml, agent cards, the manifest, and the `agents` command."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest

from dd_agent_factcheck.agent import FactChecker
from dd_agent_hello.agent import HelloWorld
from dd_agent_quality.agent import QualityReviewer
from dd_agent_stub.agent import AbstainingStub
from dd_sdk import serve
from dd_sdk.agent import Agent, describe
from dd_sdk.contract.models import GroundingMode
from dd_sdk.contract.version import CONTRACT_VERSION
from dd_sdk.wire import CARD_PATH, EXTENSION_URI
from workbench import cli
from workbench.registry import Registry, RegistryError, load_config
from workbench.remote import RemoteAgent
from workbench.settings import DEFAULT_AGENTS_CONFIG
from workbench.testing import ScriptedAgent, in_process, review_of_input

AGENTS: dict[str, Agent] = {
    "http://hello.test": HelloWorld(),
    "http://quality.test": QualityReviewer(),
    "http://factcheck.test": FactChecker(),
    "http://stub.test": AbstainingStub(),
}
IDS = {"fact.checker", "hello.world", "quality.reviewer", "stub.abstain"}


def routed(apps: dict[str, Any]) -> Any:
    """A client factory that sends each base URL to its ASGI app; any other URL is down."""

    def factory(base_url: str, timeout_s: float) -> httpx.AsyncClient:
        if base_url not in apps:
            raise httpx.ConnectError(f"connection refused: {base_url}")
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=apps[base_url]), base_url=base_url, timeout=timeout_s
        )

    return factory


def card_app(card: dict[str, Any]) -> Any:
    """An ASGI app that serves only an agent card."""

    async def app(scope: Any, receive: Any, send: Any) -> None:
        headers = [(b"content-type", b"application/json")]
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": json.dumps(card).encode()})

    return app


def fetch_card(agent: Agent, base_url: str) -> dict[str, Any]:
    """The card `dd_sdk.serve` publishes for `agent`, as JSON."""

    async def go() -> dict[str, Any]:
        app = serve.app(agent, base_url=base_url)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=base_url
        ) as hc:
            card: dict[str, Any] = (await hc.get(CARD_PATH)).json()
            return card

    return asyncio.run(go())


def write_config(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    path = tmp_path / "agents.yaml"
    path.write_text(json.dumps({"agents": entries}), encoding="utf-8")  # JSON is YAML
    return path


def registry_of(tmp_path: Path, extra: list[dict[str, Any]] | None = None) -> Registry:
    apps = {url: serve.app(agent, base_url=url) for url, agent in AGENTS.items()}
    entries = [{"url": url} for url in AGENTS] + (extra or [])
    return Registry.from_config(write_config(tmp_path, entries), client_factory=routed(apps))


@pytest.mark.requirement("DD-REGISTRY")
def test_config_lists_agents_by_url_and_the_registry_reads_each_card(tmp_path: Path) -> None:
    registry = registry_of(tmp_path)
    assert set(registry.ids()) == IDS
    assert registry.unavailable == {}
    for agent in registry:
        # Reached only through `call`, which returns the spans beside the result.
        assert isinstance(agent, RemoteAgent) and not isinstance(agent, Agent)


@pytest.mark.requirement("DD-REGISTRY")
def test_from_url_keeps_the_raw_card_it_fetched(tmp_path: Path) -> None:
    registry = registry_of(tmp_path)
    agent = registry.get("hello.world")
    assert isinstance(agent, RemoteAgent)
    assert agent.card == fetch_card(AGENTS["http://hello.test"], "http://hello.test")


@pytest.mark.requirement("DD-REGISTRY")
def test_manifest_rebuilt_from_cards_equals_each_agents_own_description(tmp_path: Path) -> None:
    registry = registry_of(tmp_path)
    by_id = {a.spec.agent_id: a for a in AGENTS.values()}
    manifest = {m["agent_id"]: m for m in registry.manifest()}
    assert set(manifest) == IDS
    for agent_id, entry in manifest.items():
        assert entry == describe(by_id[agent_id].spec)
        assert entry["grounding_mode"] in {m.value for m in GroundingMode}
        assert entry["accepts"], "an agent must accept at least one input class"
        json.dumps(entry)  # JSON-ready


@pytest.mark.requirement("DD-REGISTRY")
def test_an_unreachable_agent_is_unavailable_and_the_rest_still_load(tmp_path: Path) -> None:
    registry = registry_of(tmp_path, [{"name": "r3", "url": "http://r3.test"}])
    assert set(registry.ids()) == IDS
    assert "cannot read the agent card" in registry.unavailable["r3"]


@pytest.mark.requirement("DD-REGISTRY")
def test_a_card_without_the_spec_extension_is_rejected(tmp_path: Path) -> None:
    card = {"name": "someone-else", "capabilities": {"extensions": []}}
    path = write_config(tmp_path, [{"name": "foreign", "url": "http://foreign.test"}])
    registry = Registry.from_config(
        path, client_factory=routed({"http://foreign.test": card_app(card)})
    )
    assert len(registry) == 0
    assert EXTENSION_URI in registry.unavailable["foreign"]


@pytest.mark.requirement("DD-REGISTRY")
def test_a_card_naming_a_class_the_contract_lacks_is_rejected(tmp_path: Path) -> None:
    card = fetch_card(ScriptedAgent(GroundingMode.NONE, review_of_input), "http://odd.test")
    card["capabilities"]["extensions"][0]["params"]["accepts"] = ["Horoscope"]
    path = write_config(tmp_path, [{"name": "odd", "url": "http://odd.test"}])
    registry = Registry.from_config(
        path, client_factory=routed({"http://odd.test": card_app(card)})
    )
    assert "Horoscope" in registry.unavailable["odd"]


@pytest.mark.requirement("DD-REGISTRY")
def test_a_card_built_against_another_contract_is_incompatible_not_unavailable(
    tmp_path: Path,
) -> None:
    card = fetch_card(ScriptedAgent(GroundingMode.NONE, review_of_input), "http://old.test")
    card["capabilities"]["extensions"][0]["params"]["contract_version"] = "0.1.0"
    path = write_config(tmp_path, [{"name": "old", "url": "http://old.test"}])
    registry = Registry.from_config(
        path, client_factory=routed({"http://old.test": card_app(card)})
    )
    assert len(registry) == 0 and registry.unavailable == {}
    assert "0.1.0" in registry.incompatible["old"]
    assert CONTRACT_VERSION in registry.incompatible["old"]
    assert "old incompatible: " in registry.not_registered()


def test_a_missing_or_malformed_config_is_a_registry_error(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="not found"):
        load_config(tmp_path / "absent.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("agents:\n  - name: no-url\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="needs a `url`"):
        load_config(bad)


def test_the_shipped_config_lists_every_agent_package() -> None:
    # agents.yaml holds only URLs; run-agents.sh maps each package's script to its port.
    root = Path(__file__).resolve().parents[2]
    ports = {int(e["url"].rsplit(":", 1)[1]) for e in load_config(DEFAULT_AGENTS_CONFIG)}
    script = (root / "scripts" / "run-agents.sh").read_text()
    served = {m[0]: int(m[1]) for m in re.findall(r"\[dd-([a-z0-9]+)\]=(\d+)", script)}
    packages = {d.name for d in (root / "agents").iterdir() if (d / "pyproject.toml").exists()}
    assert set(served) == packages == {"hello", "quality", "factcheck", "stub", "r3", "director"}
    assert set(served.values()) == ports


def test_duplicate_agent_id_is_a_registry_error() -> None:
    a = in_process(ScriptedAgent(GroundingMode.NONE, review_of_input))
    b = in_process(ScriptedAgent(GroundingMode.NONE, review_of_input))
    with pytest.raises(RegistryError, match="two agents"):
        Registry.from_agents([a, b])


def test_object_without_the_protocol_is_a_registry_error() -> None:
    with pytest.raises(RegistryError, match="Agent protocol"):
        Registry.from_agents([object()])  # type: ignore[list-item]


@pytest.mark.requirement("DD-REGISTRY")
def test_agents_command_lists_the_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = registry_of(tmp_path, [{"name": "r3", "url": "http://r3.test"}])
    monkeypatch.setattr(cli, "build_registry", lambda settings: registry)
    assert cli.main(["agents"]) == 0
    out = capsys.readouterr().out
    for agent_id in IDS:
        assert agent_id in out
    assert "input_only" in out and "[r3] unavailable" in out
    assert cli.main(["agents", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {m["agent_id"] for m in data["agents"]} == IDS and "r3" in data["unavailable"]
    assert data["incompatible"] == {}

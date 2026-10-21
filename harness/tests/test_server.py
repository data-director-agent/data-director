"""The harness's own server (#55): the conductor over A2A and nothing else, configured from the
environment alone, which refuses to start on an incomplete configuration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn

from dd_harness import server
from dd_harness.identity import OperatorAssertion
from dd_harness.settings import Settings
from dd_harness.testing import PERMISSIVE, TEST_PRINCIPAL, ScriptedAgent, make_conductor
from dd_sdk.contract.models import GroundingMode

BASE = "http://testserver"
PATH_VARIABLES = ("DD_RUNS_DIR", "DD_PROFILE", "DD_AGENTS_CONFIG", "DD_SOURCES_CONFIG")
OTHER_VARIABLES = ("DD_WORKBENCH_URL", "DD_PRINCIPAL_ID", "DD_PRINCIPAL_NAME", "DD_PRINCIPAL_KIND")


@pytest.fixture
def empty_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for variable in (*PATH_VARIABLES, *OTHER_VARIABLES):
        monkeypatch.delenv(variable, raising=False)
    return monkeypatch


@pytest.fixture
def deployment(empty_env: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    """A complete configuration: an empty agent and source list, the permissive profile."""
    (tmp_path / "agents.yaml").write_text("agents: []\n", encoding="utf-8")
    (tmp_path / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    empty_env.setenv("DD_RUNS_DIR", str(tmp_path / "runs"))
    empty_env.setenv("DD_PROFILE", str(PERMISSIVE))
    empty_env.setenv("DD_AGENTS_CONFIG", str(tmp_path / "agents.yaml"))
    empty_env.setenv("DD_SOURCES_CONFIG", str(tmp_path / "sources.yaml"))
    empty_env.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    empty_env.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)
    return empty_env


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """What `uvicorn.run` was given, in place of serving it."""
    calls: dict[str, Any] = {}

    def run(app: Any, *, host: str, port: int) -> None:
        calls.update(app=app, host=host, port=port)

    monkeypatch.setattr(uvicorn, "run", run)
    return calls


def _get(app: Any, path: str) -> httpx.Response:
    async def go() -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
            return await hc.get(path)

    return asyncio.run(go())


def test_an_unset_path_stops_start_up(empty_env: pytest.MonkeyPatch, ran: dict[str, Any]) -> None:
    with pytest.raises(SystemExit, match="dd-harness: DD_RUNS_DIR unset"):
        server.main(["serve"])
    assert not ran


def test_an_unset_principal_stops_start_up(
    deployment: pytest.MonkeyPatch, ran: dict[str, Any]
) -> None:
    deployment.delenv("DD_PRINCIPAL_ID")
    with pytest.raises(SystemExit, match="DD_PRINCIPAL_ID unset"):
        server.main(["serve"])
    assert not ran


def test_a_missing_agent_list_stops_start_up(
    deployment: pytest.MonkeyPatch, ran: dict[str, Any], tmp_path: Path
) -> None:
    deployment.setenv("DD_AGENTS_CONFIG", str(tmp_path / "absent.yaml"))
    with pytest.raises(SystemExit, match="dd-harness: "):
        server.main(["serve"])
    assert not ran


def test_serve_runs_the_a2a_app_on_the_given_address(
    deployment: pytest.MonkeyPatch, ran: dict[str, Any]
) -> None:
    assert server.main(["serve", "--host", "127.0.0.1", "--port", "8123"]) == 0
    assert (ran["host"], ran["port"]) == ("127.0.0.1", 8123)
    card = _get(ran["app"], "/.well-known/agent-card.json").json()
    assert card["supportedInterfaces"][0]["url"] == "http://127.0.0.1:8123/a2a"


def test_the_configured_url_names_the_card_and_the_callback(
    deployment: pytest.MonkeyPatch, ran: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    deployment.setenv("DD_WORKBENCH_URL", "https://harness.example.org")
    built: dict[str, Any] = {}
    serving = server.serving

    def spy(settings: Settings, base_url: str) -> Any:
        built["conductor"], authenticator = serving(settings, base_url)
        return built["conductor"], authenticator

    monkeypatch.setattr(server, "serving", spy)
    server.main(["serve", "--host", "0.0.0.0"])
    assert built["conductor"].workbench_url == "https://harness.example.org"
    card = _get(ran["app"], "/.well-known/agent-card.json").json()
    assert card["supportedInterfaces"][0]["url"] == "https://harness.example.org/a2a"


def test_a_host_beyond_loopback_is_warned_about(
    deployment: pytest.MonkeyPatch, ran: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    server.main(["serve", "--host", "0.0.0.0"])
    assert "trusted network only" in capsys.readouterr().err
    server.main(["serve"])
    assert capsys.readouterr().err == ""


def test_serving_sets_the_callback_to_the_base_url(deployment: pytest.MonkeyPatch) -> None:
    conductor, authenticator = server.serving(Settings.from_env(), "http://127.0.0.1:9000")
    assert conductor.workbench_url == "http://127.0.0.1:9000"
    assert authenticator.principal_for(None) == TEST_PRINCIPAL


def test_the_app_serves_a2a_and_nothing_else(tmp_path: Path) -> None:
    agent = ScriptedAgent(GroundingMode.NONE, RuntimeError("not run"))
    conductor = make_conductor(tmp_path / "runs", agent)
    app = server.build_app(conductor, OperatorAssertion(TEST_PRINCIPAL), BASE)
    card = _get(app, "/.well-known/agent-card.json")
    assert card.status_code == 200
    assert [s["id"] for s in card.json()["skills"]] == ["fake.none"]
    # The workbench's routes are not the harness's.
    for path in ("/runs", "/conversations", "/agents", "/viewer/", "/"):
        assert _get(app, path).status_code == 404, path

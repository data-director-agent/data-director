"""The harness's own server (#55): the conductor over A2A and nothing else, configured from the
environment alone, which refuses to start on an incomplete configuration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from starlette.applications import Starlette

from dd_harness import server
from dd_harness.identity import OperatorAssertion
from dd_harness.settings import Settings
from dd_harness.testing import (
    PERMISSIVE,
    TEST_PRINCIPAL,
    AbstainingStub,
    ScriptedAgent,
    make_conductor,
    request,
)
from dd_harness.testing.serving import send_to_harness
from dd_harness.transport.a2a import a2a_routes
from dd_sdk import serve
from dd_sdk.contract.models import GroundingMode, InvocationRequest, to_document
from dd_sdk.wire import META_DELEGATION_TOKEN

BASE = "http://testserver"
PATH_VARIABLES = ("DD_RUNS_DIR", "DD_PROFILE", "DD_AGENTS_CONFIG", "DD_SOURCES_CONFIG")
OTHER_VARIABLES = (
    "DD_HARNESS_URL",
    "DD_PRINCIPAL_ID",
    "DD_PRINCIPAL_NAME",
    "DD_PRINCIPAL_KIND",
    "DD_OIDC_ISSUER",
    "DD_OIDC_CLIENT_ID",
)


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
    deployment.setenv("DD_HARNESS_URL", "https://harness.example.org")
    built: dict[str, Any] = {}
    serving = server.serving

    def spy(settings: Settings, base_url: str) -> Any:
        built["conductor"], authenticator = serving(settings, base_url)
        return built["conductor"], authenticator

    monkeypatch.setattr(server, "serving", spy)
    server.main(["serve", "--host", "0.0.0.0"])
    assert built["conductor"].harness_url == "https://harness.example.org"
    card = _get(ran["app"], "/.well-known/agent-card.json").json()
    assert card["supportedInterfaces"][0]["url"] == "https://harness.example.org/a2a"


def test_a_host_beyond_loopback_is_warned_about(
    deployment: pytest.MonkeyPatch, ran: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    server.main(["serve", "--host", "0.0.0.0"])
    assert "trusted network only" in capsys.readouterr().err
    server.main(["serve"])
    assert capsys.readouterr().err == ""


def test_a_server_that_signs_callers_in_is_not_warned_about(
    deployment: pytest.MonkeyPatch, ran: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    deployment.delenv("DD_PRINCIPAL_ID")
    deployment.delenv("DD_PRINCIPAL_NAME")
    deployment.setenv("DD_OIDC_ISSUER", "https://sandbox.orcid.org")
    deployment.setenv("DD_OIDC_CLIENT_ID", "APP-TESTCLIENT0000")
    server.main(["serve", "--host", "0.0.0.0"])
    assert capsys.readouterr().err == ""


def test_a_provider_beside_the_operator_stops_start_up(
    deployment: pytest.MonkeyPatch, ran: dict[str, Any]
) -> None:
    deployment.setenv("DD_OIDC_ISSUER", "https://sandbox.orcid.org")
    deployment.setenv("DD_OIDC_CLIENT_ID", "APP-TESTCLIENT0000")
    with pytest.raises(SystemExit, match="both set"):
        server.main(["serve"])
    assert not ran


def test_serving_sets_the_callback_to_the_base_url(deployment: pytest.MonkeyPatch) -> None:
    conductor, authenticator = server.serving(Settings.from_env(), "http://127.0.0.1:9000")
    assert conductor.harness_url == "http://127.0.0.1:9000"
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


def _rpc(app: Any, method: str, params: dict[str, Any]) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
            body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            response = await hc.post("/a2a", json=body, headers={"A2A-Version": "1.0"})
            found: dict[str, Any] = response.json()
            return found

    return asyncio.run(go())


def _task_methods(task_id: str) -> list[tuple[str, dict[str, Any]]]:
    return [
        ("ListTasks", {"includeArtifacts": True}),
        ("GetTask", {"id": task_id}),
        ("CancelTask", {"id": task_id}),
        ("SubscribeToTask", {"id": task_id}),
    ]


def _every_a2a_server(tmp_path: Path) -> list[tuple[Any, InvocationRequest]]:
    """The harness's A2A app, as served alone and as the app serves it (callbacks only), and an
    agent's own server (`dd_sdk.serve`), each with a request it answers."""
    stub = AbstainingStub()
    conductor = make_conductor(tmp_path / "runs", stub)
    harness_request = request(stub.spec.agent_id)
    _card, callbacks_only = a2a_routes(conductor, None, BASE)
    return [
        (server.build_app(conductor, OperatorAssertion(TEST_PRINCIPAL), BASE), harness_request),
        (Starlette(routes=callbacks_only), harness_request),
        (serve.app(AbstainingStub(), base_url=BASE), harness_request),
    ]


def test_no_caller_can_read_back_a_task_or_the_grant_it_carried(tmp_path: Path) -> None:
    # Callers are not authenticated to A2A's task store, so a kept task would give any caller
    # another's request, reply and delegation grant (docs/specs/transport.md).
    for app, sent in _every_a2a_server(tmp_path):
        ordinary = send_to_harness(app, BASE, sent)
        delegated = send_to_harness(app, BASE, sent, metadata={META_DELEGATION_TOKEN: "a-grant"})
        for task in (ordinary, delegated):
            assert task is not None
            for method, params in _task_methods(task.id):
                answer = _rpc(app, method, params)
                assert "result" not in answer, (method, answer)
                assert "a-grant" not in str(answer)


def test_a_message_may_not_continue_an_earlier_task(tmp_path: Path) -> None:
    for app, sent in _every_a2a_server(tmp_path):
        task = send_to_harness(app, BASE, sent)
        assert task is not None
        message = {
            "messageId": "m-2",
            "role": "ROLE_USER",
            "taskId": task.id,
            "parts": [{"data": to_document(sent)}],
        }
        answer = _rpc(app, "SendMessage", {"message": message})
        assert "result" not in answer, answer

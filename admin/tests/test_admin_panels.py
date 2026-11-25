"""The admin service's LLM gateway and model broker pages (docs/guide/operations/admin.md): what
each shows of a gateway or broker that answers, that does not, and that is not configured, and
that no key or credential reaches a page."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from dd_admin import broker, gateway
from dd_admin.agents import Agents, AgentState
from dd_admin.app import Admin, build_app
from dd_admin.settings import AdminSettings
from dd_admin.system import Done, System

GATEWAY = "http://127.0.0.1:4000"
GATEWAY_KEY = "sk-viewer-not-to-be-shown"
KEY_TOKEN = "hashed-token-not-to-be-shown"
BROKER = "http://127.0.0.1:8300"
BROKER_CREDENTIAL = "operator-credential-not-to-be-shown"
SONNET = "claude-sonnet-5-5"


def model_info() -> dict[str, Any]:
    return {
        "data": [
            {
                "model_name": SONNET,
                "litellm_params": {"model": f"anthropic/{SONNET}", "rpm": 50},
                "model_info": {
                    "input_cost_per_token": 3e-6,
                    "output_cost_per_token": 15e-6,
                    "litellm_provider": "anthropic",
                    "max_input_tokens": 200000,
                },
            },
            {"model_name": "llama-local", "litellm_params": {"model": "ollama_chat/llama3.1"}},
        ]
    }


def key_row(alias: str, spend: float, budget: float | None, **extra: Any) -> dict[str, Any]:
    return {
        "token": KEY_TOKEN,
        "key_name": "sk-...abcd",
        "key_alias": alias,
        "spend": spend,
        "max_budget": budget,
        "budget_duration": "30d",
        "budget_reset_at": "2026-12-01T00:00:00Z",
        "models": [SONNET],
        "rpm_limit": 60,
        "team_id": "team-1",
        **extra,
    }


def broker_summary() -> dict[str, Any]:
    today = datetime.now(UTC).date()
    return {
        "since": (today - timedelta(days=29)).isoformat(),
        "days": 30,
        "accounts_by_provider": {"anthropic": 2, "openai": 1},
        "people_with_usage": 4,
        "usage": [
            {
                "day": today.isoformat(),
                "payer": "deployment",
                "provider": "anthropic",
                "model": SONNET,
                "input_tokens": 1000,
                "output_tokens": 100,
            },
            {
                "day": today.isoformat(),
                "payer": "own",
                "provider": "openai",
                "model": "gpt-5",
                "input_tokens": 50,
                "output_tokens": 5,
            },
        ],
        "agents": ["advisor.policy", "advisor.standards"],
        "providers_paid": ["anthropic"],
        "deployment_base_url": True,
        "allowed_base_urls": ["https://models.example.ac.uk"],
        "private_base_urls": [],
    }


@dataclass
class FakeSystem(System):
    """The gateway and the broker as they answer over HTTP; `None` for one that is down."""

    gateway_up: bool = True
    broker_up: bool = True
    summary: dict[str, Any] | None = field(default_factory=broker_summary)
    sent: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    def run(self, *cmd: str, timeout_s: float = 60.0) -> Done:
        return Done(127, "", "not here")

    def get_json(self, url: str, headers: Any = None) -> object | None:
        self.sent.append((url, dict(headers or {})))
        if url.startswith(GATEWAY):
            return self._gateway(url) if self.gateway_up else None
        if url.startswith(BROKER):
            return self._broker(url, dict(headers or {})) if self.broker_up else None
        return None

    def _gateway(self, url: str) -> object | None:
        path = url.removeprefix(GATEWAY).split("?", 1)[0]
        documents: dict[str, object] = {
            "/health/readiness": {"status": "healthy", "db": "connected", "litellm_version": "1.1"},
            "/model/info": model_info(),
            "/key/list": {
                "keys": [
                    key_row("advisor-standards", 9.5, 10.0),
                    key_row("model-broker", 1.0, None, blocked=True),
                ],
                "total_pages": 1,
            },
            "/team/list": [{"team_id": "team-1", "team_alias": "agents", "spend": 10.5}],
            "/user/list": {"users": [{"user_id": "dd-admin", "user_role": "proxy_admin_viewer"}]},
        }
        return documents.get(path)

    def _broker(self, url: str, headers: dict[str, str]) -> object | None:
        if url.endswith("/healthz"):
            return {"status": "ok"}
        if url.endswith("/admin/summary"):
            ok = headers.get("Authorization") == f"Bearer {BROKER_CREDENTIAL}"
            return self.summary if ok else None
        return None


@pytest.fixture
def system() -> FakeSystem:
    return FakeSystem()


@pytest.fixture
def client(system: FakeSystem, tmp_path: Path) -> TestClient:
    (tmp_path / "litellm-key").write_text(GATEWAY_KEY + "\n")
    (tmp_path / "broker-key").write_text(BROKER_CREDENTIAL + "\n")
    settings = AdminSettings(
        litellm_url=GATEWAY,
        litellm_key_file=tmp_path / "litellm-key",
        broker_url=BROKER,
        broker_key_file=tmp_path / "broker-key",
    )
    return TestClient(build_app(Admin.open(settings, system)), base_url="http://localhost:8200")


def unconfigured() -> TestClient:
    return TestClient(
        build_app(Admin.open(AdminSettings(), FakeSystem())), base_url="http://localhost"
    )


# --- Both pages ----------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/gateway", "/broker"])
def test_each_page_answers_get_and_nothing_that_could_change_state(
    client: TestClient, path: str
) -> None:
    assert client.get(path).status_code == 200
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, path).status_code == 405


def test_no_key_token_or_credential_reaches_a_page(client: TestClient) -> None:
    for path in ("/", "/gateway", "/broker", "/spend", "/config"):
        page = client.get(path).text
        for secret in (GATEWAY_KEY, KEY_TOKEN, "sk-...abcd", BROKER_CREDENTIAL):
            assert secret not in page, (path, secret)


@pytest.mark.parametrize(
    ("path", "setting"), [("/gateway", "DD_ADMIN_LITELLM_URL"), ("/broker", "DD_ADMIN_BROKER_URL")]
)
def test_unconfigured_each_page_names_its_setting_and_asks_nothing(path: str, setting: str) -> None:
    system = FakeSystem()
    http = TestClient(build_app(Admin.open(AdminSettings(), system)), base_url="http://localhost")
    response = http.get(path)
    assert response.status_code == 200 and setting in response.text
    assert not [url for url, _ in system.sent if url.startswith((GATEWAY, BROKER))]


def test_the_overview_shows_both_and_neither_when_unconfigured(client: TestClient) -> None:
    page = client.get("/").text
    assert 'href="/gateway"' in page.split("<main", 1)[1]
    assert 'href="/broker"' in page.split("<main", 1)[1]
    plain = unconfigured().get("/").text.split("<main", 1)[1]
    assert 'href="/gateway"' not in plain and 'href="/broker"' not in plain


# --- The gateway ---------------------------------------------------------------------------------


def test_a_gateway_without_a_key_is_named_not_called(system: FakeSystem) -> None:
    settings = AdminSettings(litellm_url=GATEWAY, litellm_key_file=None)
    assert gateway.read_state(settings, system).error  # no key: named, not called
    assert not system.sent


def test_the_gateway_page_shows_its_setup(
    client: TestClient, system: FakeSystem, tmp_path: Path
) -> None:
    state = gateway.read_state(
        AdminSettings(litellm_url=GATEWAY, litellm_key_file=tmp_path / "litellm-key"), system
    )
    assert state.answered and state.ready and state.database == "connected"
    models = {m.name: m for m in state.models}
    assert set(models) == {"llama-local", SONNET}
    sonnet = models[SONNET]
    assert sonnet.price is not None and sonnet.provider == "anthropic" and sonnet.rpm == 50
    assert models["llama-local"].price is None and models["llama-local"].provider == "ollama_chat"
    assert [k.name for k in state.keys] == ["advisor-standards", "model-broker"]
    assert state.keys[0].budget.state == "warn"  # $9.50 of $10
    assert state.keys[1].blocked and state.keys[1].budget.state == "none"
    assert [t.name for t in state.teams] == ["agents"]
    assert [u.role for u in state.users] == ["proxy_admin_viewer"]
    page = client.get("/gateway").text
    assert SONNET in page and "advisor-standards" in page and "scripts/admin.py" in page


def test_a_gateway_part_that_does_not_answer_is_named_and_the_rest_shown(
    system: FakeSystem, tmp_path: Path
) -> None:
    original = system._gateway

    def without_users(url: str) -> object | None:
        return None if "/user/list" in url else original(url)

    system._gateway = without_users  # type: ignore[method-assign]
    (tmp_path / "key").write_text(GATEWAY_KEY)
    state = gateway.read_state(
        AdminSettings(litellm_url=GATEWAY, litellm_key_file=tmp_path / "key"), system
    )
    assert state.answered and state.keys and not state.users
    assert len(state.problems) == 1


def test_a_gateway_that_does_not_answer_is_named(client: TestClient, system: FakeSystem) -> None:
    system.gateway_up = False
    response = client.get("/gateway", params={"fresh": "1"})
    assert response.status_code == 200 and GATEWAY in response.text


def test_the_key_list_is_read_page_by_page(tmp_path: Path) -> None:
    pages = {1: ["a", "b"], 2: ["c"]}

    @dataclass
    class Paged(FakeSystem):
        def _gateway(self, url: str) -> object | None:
            if "/key/list" in url:
                page = int(url.split("page=", 1)[1].split("&", 1)[0])
                return {
                    "keys": [key_row(a, 0, None) for a in pages[page]],
                    "total_pages": len(pages),
                }
            return super()._gateway(url)

    (tmp_path / "key").write_text(GATEWAY_KEY)
    state = gateway.read_state(
        AdminSettings(litellm_url=GATEWAY, litellm_key_file=tmp_path / "key"), Paged()
    )
    assert sorted(k.name for k in state.keys) == ["a", "b", "c"]


# --- The broker ----------------------------------------------------------------------------------


def test_the_broker_summary_is_read_with_the_operators_credential(
    client: TestClient, system: FakeSystem
) -> None:
    page = client.get("/broker").text
    assert "advisor.standards" in page and SONNET in page
    [summary] = [h for url, h in system.sent if url.endswith("/admin/summary")]
    assert summary == {"Authorization": f"Bearer {BROKER_CREDENTIAL}"}
    [health] = [h for url, h in system.sent if url.endswith("/healthz")]
    assert health == {}


def test_the_broker_summary_is_summed_by_day_payer_and_model() -> None:
    found = broker.BrokerState(configured=True)
    broker.summarise(broker_summary(), found)
    assert found.accounts_by_provider == {"anthropic": 2, "openai": 1}
    assert len(found.per_day) == 30 and sum(n for _, n in found.per_day) == 1155
    assert found.by_payer["deployment"].total == 1100 and found.by_payer["own"].total == 55
    assert found.by_model[0][:3] == ("anthropic", SONNET, "deployment")
    assert found.through_base_url and found.providers_paid == ["anthropic"]


def test_a_broker_up_without_a_credential_says_how_to_give_it_one(
    system: FakeSystem, tmp_path: Path
) -> None:
    found = broker.read_broker(AdminSettings(broker_url=BROKER), system)
    assert found.answered and not found.summarised
    assert "broker-admin-credential.sh" in (found.summary_error or "")
    (tmp_path / "wrong").write_text("another-credential")
    refused = broker.read_broker(
        AdminSettings(broker_url=BROKER, broker_key_file=tmp_path / "wrong"), system
    )
    assert refused.answered and refused.summary_error


def test_a_broker_that_does_not_answer_is_named(client: TestClient, system: FakeSystem) -> None:
    system.broker_up = False
    response = client.get("/broker", params={"fresh": "1"})
    assert response.status_code == 200 and BROKER in response.text


def test_coverage_names_model_backed_agents_without_a_credential() -> None:
    found = broker.BrokerState(configured=True)
    broker.summarise(broker_summary(), found)
    agents = Agents(
        agents=[
            AgentState("advisor-standards", "u", "up", described={"models": [{"model": "m"}]}),
            AgentState("advisor-rights", "u", "up", described={"models": [{"model": "m"}]}),
            AgentState("advisor-files", "u", "up", described={"models": []}),
            AgentState("advisor-ethics", "u", "down"),
        ]
    )
    found_coverage = broker.coverage(found, agents)
    assert found_coverage is not None
    assert found_coverage.missing == ["advisor.rights"]
    assert found_coverage.unused == ["advisor.policy"]


def test_the_broker_key_defaults_to_the_units_credential(tmp_path: Path) -> None:
    env = {"DD_ADMIN_BROKER_URL": BROKER + "/", "CREDENTIALS_DIRECTORY": str(tmp_path)}
    assert AdminSettings.from_env(env).broker_key_file is None
    (tmp_path / "model-broker-admin").write_text(BROKER_CREDENTIAL)
    found = AdminSettings.from_env(env)
    assert found.broker_key_file == tmp_path / "model-broker-admin"
    assert found.broker_url == BROKER

"""The admin service's Monitoring page (docs/guide/operations/admin.md): links to the services
that run beside the deployment, whether each answers, and the alerts it reports. A service with no
setting is linked at its tunnel address and not asked; one that does not answer is named and the
rest still shows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from starlette.testclient import TestClient

from dd_admin import monitoring
from dd_admin.app import Admin, build_app
from dd_admin.settings import AdminSettings
from dd_admin.system import Done, System
from dd_harness.settings import SettingsError

GRAFANA = "https://grafana.example.ac.uk"
PROMETHEUS = "http://127.0.0.1:9090"
ALERTMANAGER = "http://127.0.0.1:9093"
GATEWAY = "http://127.0.0.1:4000"


def firing(name: str = "KeyOutOfBudget", state: str = "firing") -> dict[str, Any]:
    return {
        "labels": {"alertname": name, "severity": "critical"},
        "annotations": {"summary": "advisor-standards has spent its budget"},
        "state": state,
        "activeAt": "2026-11-24T09:00:00.123456789Z",
    }


@dataclass
class FakeSystem(System):
    """Grafana, Prometheus and Alertmanager as they answer over HTTP; None for a service down."""

    up: set[str] = field(default_factory=lambda: {"grafana", "prometheus", "alertmanager"})
    alerts: list[dict[str, Any]] = field(default_factory=lambda: [firing()])
    asked: list[str] = field(default_factory=list)

    def run(self, *cmd: str, timeout_s: float = 60.0) -> Done:
        return Done(127, "", "not here")

    def get_json(self, url: str, headers: Any = None) -> object | None:
        self.asked.append(url)
        if url.startswith(GRAFANA):
            return {"database": "ok"} if "grafana" in self.up else None
        if url.startswith(PROMETHEUS):
            if "prometheus" not in self.up:
                return None
            return {"status": "success", "data": {"alerts": self.alerts}}
        if url.startswith(ALERTMANAGER):
            if "alertmanager" not in self.up:
                return None
            return [
                {
                    "labels": {"alertname": "SpendRateHigh", "severity": "warning"},
                    "annotations": {"summary": "over $20 an hour"},
                    "startsAt": "2026-11-24T08:00:00Z",
                }
            ]
        return None


SETTINGS = AdminSettings(
    grafana_url=GRAFANA,
    prometheus_url=PROMETHEUS,
    alertmanager_url=ALERTMANAGER,
    litellm_url=GATEWAY,
)


def open_client(system: FakeSystem, settings: AdminSettings = SETTINGS) -> TestClient:
    return TestClient(build_app(Admin.open(settings, system)), base_url="http://localhost:8200")


@pytest.fixture
def system() -> FakeSystem:
    return FakeSystem()


def main(page: str) -> str:
    return page.split("<main", 1)[1]


# --- The page ------------------------------------------------------------------------------------


def test_the_page_answers_get_and_nothing_that_could_change_state(system: FakeSystem) -> None:
    http = open_client(system)
    assert http.get("/monitoring").status_code == 200
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert http.request(method, "/monitoring").status_code == 405


def test_each_configured_service_is_linked_safely_and_asked(system: FakeSystem) -> None:
    page = main(open_client(system).get("/monitoring").text)
    for url in (GRAFANA, PROMETHEUS, ALERTMANAGER, f"{GATEWAY}/ui"):
        assert f'href="{url}"' in page
    assert page.count('rel="noreferrer noopener"') == 4
    assert page.count("answering") >= 3
    assert any(url.startswith(GRAFANA) for url in system.asked)


def test_alerts_from_prometheus_and_alertmanager_are_listed(system: FakeSystem) -> None:
    page = main(open_client(system).get("/monitoring").text)
    assert "KeyOutOfBudget" in page and "SpendRateHigh" in page
    assert "advisor-standards has spent its budget" in page


def test_a_service_that_does_not_answer_is_named_and_the_rest_still_shows(
    system: FakeSystem,
) -> None:
    system.up.discard("prometheus")
    page = main(open_client(system).get("/monitoring").text)
    assert "not answering" in page and "SpendRateHigh" in page
    assert "KeyOutOfBudget" not in page


def test_a_service_without_a_setting_is_linked_at_its_tunnel_address_and_not_asked(
    system: FakeSystem,
) -> None:
    http = open_client(system, AdminSettings())
    page = main(http.get("/monitoring").text)
    assert 'href="http://localhost:3000"' in page and "DD_ADMIN_GRAFANA_URL" in page
    assert system.asked == []
    assert "/ui" not in page  # no gateway configured, so no link to its page


def test_langfuse_is_linked_only_when_set(system: FakeSystem) -> None:
    assert "Langfuse" not in main(open_client(system).get("/monitoring").text)
    settings = AdminSettings(langfuse_url="https://langfuse.example.ac.uk")
    assert "Langfuse" in main(open_client(system, settings).get("/monitoring").text)


def test_a_long_list_of_alerts_is_cut_and_says_so(system: FakeSystem) -> None:
    system.alerts = [firing(f"Alert{n}") for n in range(monitoring.MAX_ALERTS + 3)]
    link = monitoring.read(SETTINGS, system).links[1]
    assert len(link.alerts) == monitoring.MAX_ALERTS and link.more_alerts == 3


# --- The overview --------------------------------------------------------------------------------


def test_the_overview_counts_firing_alerts_only_once_a_service_is_configured(
    system: FakeSystem,
) -> None:
    assert 'href="/monitoring"' in main(open_client(system).get("/").text)
    plain = main(open_client(FakeSystem(), AdminSettings()).get("/").text)
    assert "Alerts firing" not in plain


def test_firing_counts_only_firing_alerts() -> None:
    system = FakeSystem(alerts=[firing(), firing("Soon", state="pending")])
    assert monitoring.read(SETTINGS, system).firing == 1


def test_firing_is_unknown_when_nothing_answers() -> None:
    assert monitoring.read(SETTINGS, FakeSystem(up=set())).firing is None


# --- The settings --------------------------------------------------------------------------------


def test_a_monitoring_address_is_trimmed_and_kept() -> None:
    settings = AdminSettings.from_env({"DD_ADMIN_GRAFANA_URL": f" {GRAFANA}/ "})
    assert settings.grafana_url == GRAFANA and settings.prometheus_url is None


@pytest.mark.parametrize(
    "value", ["javascript:alert(1)", "grafana.example.ac.uk", "https://user:pw@example.ac.uk"]
)
def test_an_address_that_is_not_a_plain_web_address_is_refused(value: str) -> None:
    with pytest.raises(SettingsError):
        AdminSettings.from_env({"DD_ADMIN_ALERTMANAGER_URL": value})

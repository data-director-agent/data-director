"""`GET /api/about` is open, so it retries the missing agents at most once per interval (#726)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from support import configure_env, dist_dir, new_governance

from dd_app.app import build_app
from dd_app.governance import ABOUT_REFRESH_INTERVAL_S, Governance


class CountingRegistry:
    """Stands in for the registry: counts refreshes, and finds an agent once it is `up`."""

    def __init__(self) -> None:
        self.refreshes = 0
        self.unavailable: dict[str, str] = {"late": "http://10.0.0.9:8199/ refused"}
        self.incompatible: dict[str, str] = {}
        self.up = False

    def refresh(self) -> None:
        self.refreshes += 1
        if self.up:
            self.unavailable = {}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    yield from new_governance()


@pytest.fixture
def registry(governance: Governance) -> CountingRegistry:
    double = CountingRegistry()
    governance.conductor.registry = double  # type: ignore[assignment]
    return double


@pytest.fixture
def clock(governance: Governance) -> Clock:
    fake = Clock()
    governance.clock = fake
    return fake


def test_a_run_of_requests_refreshes_once(
    governance: Governance, registry: CountingRegistry, clock: Clock
) -> None:
    for _ in range(50):
        assert governance.deployment()["unavailable"] == ["late"]
    assert registry.refreshes == 1


def test_it_refreshes_again_once_the_interval_has_passed(
    governance: Governance, registry: CountingRegistry, clock: Clock
) -> None:
    governance.deployment()
    clock.now += ABOUT_REFRESH_INTERVAL_S - 1
    governance.deployment()
    assert registry.refreshes == 1
    clock.now += 1
    governance.deployment()
    assert registry.refreshes == 2


def test_an_agent_that_became_available_is_reported_within_one_interval(
    governance: Governance, registry: CountingRegistry, clock: Clock
) -> None:
    assert governance.deployment()["unavailable"] == ["late"]
    registry.up = True
    clock.now += ABOUT_REFRESH_INTERVAL_S - 1
    assert governance.deployment()["unavailable"] == ["late"]
    clock.now += 1
    assert governance.deployment()["unavailable"] == []


def test_a_request_during_a_refresh_does_not_wait_for_it(
    governance: Governance, registry: CountingRegistry, clock: Clock
) -> None:
    seen: list[list[str]] = []

    def slow_refresh() -> None:
        registry.refreshes += 1
        seen.append(governance.deployment()["unavailable"])  # a second request, mid-refresh

    registry.refresh = slow_refresh  # type: ignore[method-assign]
    governance.deployment()
    assert registry.refreshes == 1
    assert seen == [["late"]]


def test_anonymous_requests_to_the_endpoint_refresh_once(
    governance: Governance, clock: Clock, tmp_path: Path
) -> None:
    client = TestClient(build_app(governance, dist_dir(tmp_path)))
    # Swapped in after the app is built, which reads the real registry's manifest.
    registry = CountingRegistry()
    governance.conductor.registry = registry  # type: ignore[assignment]
    for _ in range(20):
        assert client.get("/api/about").status_code == 200
    assert registry.refreshes == 1

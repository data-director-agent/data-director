"""`serve --reload`: uvicorn restarts the agent from an import string when its files change."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import uvicorn
from starlette.testclient import TestClient

from dd_sdk import serve
from dd_sdk.agent import Agent, AgentResult, AgentSpec, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import GroundingMode, InvocationRequest, Message


class Echo:
    spec = AgentSpec(
        agent_id="test.reload",
        version="0.0.0",
        description="An agent for testing reload.",
        action_class="advise",
        accepts=(ClassSchema.of(Message),),
        grounding_mode=GroundingMode.NONE,
        payload=None,
    )

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        raise NotImplementedError


BUILT: list[Agent] = []


def build() -> Agent:
    BUILT.append(Echo())
    return BUILT[-1]


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    calls: dict[str, Any] = {}

    def run(target: Any, **kwargs: Any) -> None:
        calls.update(kwargs, target=target)

    monkeypatch.setattr(uvicorn, "run", run)
    # Set, so that monkeypatch restores what `main` writes there.
    monkeypatch.setenv(serve.BUILD_ENV, "")
    monkeypatch.setenv(serve.BASE_URL_ENV, "")
    return calls


def test_without_reload_the_app_itself_is_served(ran: dict[str, Any]) -> None:
    assert serve.main(build, ["serve", "--port", "8199"]) == 0
    assert not isinstance(ran["target"], str)
    assert "reload" not in ran


def test_reload_serves_a_factory_that_watches_the_agents_package_and_its_prompts(
    ran: dict[str, Any],
) -> None:
    assert serve.main(build, ["serve", "--port", "8199", "--reload"]) == 0
    assert ran["target"] == "dd_sdk.serve:reloadable_app"
    assert ran["factory"] is True and ran["reload"] is True
    assert str(Path(__file__).parent) in ran["reload_dirs"]
    assert "*.md" in ran["reload_includes"]


def test_the_factory_builds_the_agent_the_environment_names(
    ran: dict[str, Any],
) -> None:
    serve.main(build, ["serve", "--port", "8199", "--reload"])
    BUILT.clear()
    card = TestClient(serve.reloadable_app()).get("/.well-known/agent-card.json")
    assert len(BUILT) == 1
    assert "test.reload" in card.text and "http://127.0.0.1:8199" in card.text

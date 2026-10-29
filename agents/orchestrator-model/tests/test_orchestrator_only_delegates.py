"""The orchestrator's model has no tools except its delegations (ADR-0012 decision 15).

These tests fail if the model is offered a way to the outside world that is not a delegation
through the harness: an MCP server, a server tool such as web search or code execution, Agent
Skills, or a dependency or import that could provide one. An external source is reached through
an agent, whose run is governed and recorded. Change the decision, not these tests."""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path
from typing import Any, ClassVar

import pytest

from dd_agent_example_hello.agent import HelloWorld
from dd_agent_orchestrator_model.agent import ModelOrchestrator
from dd_agent_orchestrator_model.model import FALLBACK_BETA, AnthropicModel
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import Message, OutcomeStatus

PACKAGE = Path(__file__).resolve().parents[1]
SOURCE = PACKAGE / "src" / "dd_agent_orchestrator_model"

# Every argument the orchestrator may send to the Messages API. `mcp_servers`, `container` (which
# carries Agent Skills) and the like are absent on purpose.
REQUEST_KEYS = {
    "model",
    "max_tokens",
    "system",
    "messages",
    "tools",
    "tool_choice",
    "output_config",
    "betas",
    "fallbacks",
}
# A client tool, which the orchestrator runs as a delegation. A server tool has a `type`.
TOOL_KEYS = {"name", "description", "input_schema"}
DEPENDENCIES = {"data-director-sdk", "anthropic"}
IMPORTS = {"anthropic", "dd_sdk", "dd_agent_orchestrator_model", "__future__"}


class _Block:
    type = "text"
    text = "Hello."

    def model_dump(self, **_: Any) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


class _Usage:
    input_tokens = 10
    output_tokens = 2
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class _Response:
    stop_reason = "end_turn"
    stop_details = None
    content: ClassVar[list[_Block]] = [_Block()]
    model = "claude-sonnet-5-5"
    usage = _Usage()


class _RecordingClient:
    """Stands in for `anthropic.Anthropic`, keeping each request it is sent."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.beta = self
        self.messages = self

    def create(self, **kwargs: Any) -> _Response:
        self.requests.append(kwargs)
        return _Response()


@pytest.mark.requirement("DD-DELEGATION")
def test_the_model_is_offered_only_delegations(runs_dir: Path) -> None:
    client = _RecordingClient()
    orchestrator = ModelOrchestrator(AnthropicModel(client))  # type: ignore[arg-type]
    conductor = make_conductor(runs_dir, orchestrator, HelloWorld())

    env = conductor.invoke(
        request("orchestrator.model", Message(message_text="Please greet Ada")),
        acting_for=TEST_PRINCIPAL,
    )

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    [sent] = client.requests
    assert set(sent) <= REQUEST_KEYS, f"unexpected request arguments: {set(sent) - REQUEST_KEYS}"
    assert sent["betas"] == [FALLBACK_BETA]
    assert sent["tools"], "the manifest's agent should be offered as a tool"
    for tool in sent["tools"]:
        assert set(tool) == TOOL_KEYS, f"{tool.get('name')} is not a delegation tool"
        assert tool["description"].startswith("Ask the agent ")


@pytest.mark.requirement("DD-DELEGATION")
def test_the_package_depends_only_on_the_sdk_and_the_model_client() -> None:
    project = tomllib.loads((PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    names = {_name(d) for d in project["dependencies"]}
    assert names == DEPENDENCIES
    assert not project.get("optional-dependencies")


@pytest.mark.requirement("DD-DELEGATION")
@pytest.mark.parametrize("path", sorted(SOURCE.glob("*.py")), ids=lambda p: p.name)
def test_the_source_imports_only_the_standard_library_the_sdk_and_the_model_client(
    path: Path,
) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots = [node.module.split(".")[0]]
        else:
            continue
        for root in roots:
            assert root in IMPORTS or root in sys.stdlib_module_names, f"{path.name} imports {root}"


def _name(requirement: str) -> str:
    for mark in "<>=!~[; ":
        requirement = requirement.split(mark)[0]
    return requirement.strip().lower()

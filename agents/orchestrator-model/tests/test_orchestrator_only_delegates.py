"""The orchestrator's model has no tools except its delegations and `ask_questions`,
`name_project` and `set_entry_point`, which run nothing (docs/specs/orchestration.md).

These tests fail if the model is offered a way to the outside world that is not a delegation
through the harness: an MCP server, a server tool such as web search or code execution, Agent
Skills, or a dependency or import that could provide one. An external source is reached through
an agent, whose run is governed and recorded. Change the decision, not these tests.

They hold for each provider's adapter: Claude through the Messages API, and every other provider
through an OpenAI-compatible Chat Completions endpoint (#831). The package calls its model through
the SDK's model seam and imports no provider's client itself."""

from __future__ import annotations

import ast
import json
import sys
import tomllib
from pathlib import Path
from typing import Any, ClassVar

import httpx2 as httpx
import pytest

from dd_agent_example_hello.agent import HelloWorld
from dd_agent_orchestrator_model.agent import (
    ENTRY_TOOL,
    ENTRY_TOOL_DEFINITION,
    NAME_TOOL,
    NAME_TOOL_DEFINITION,
    QUESTIONS_TOOL,
    QUESTIONS_TOOL_DEFINITION,
    ModelOrchestrator,
)
from dd_harness.projects import ProjectStore
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import Message, OutcomeStatus
from dd_sdk.model import Model
from dd_sdk.model_anthropic import FALLBACK_BETA, AnthropicModel
from dd_sdk.model_openai import OpenAIModel, openai_client

PACKAGE = Path(__file__).resolve().parents[1]
SOURCE = PACKAGE / "src" / "dd_agent_orchestrator_model"

# Every argument the orchestrator may send to the Messages API. `mcp_servers`, `container` (which
# carries Agent Skills) and the like are absent on purpose.
ANTHROPIC_KEYS = {
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
# Every field the orchestrator may send to a Chat Completions endpoint. `web_search_options`,
# `audio`, `functions` (the older way to give tools) and the like are absent on purpose.
OPENAI_KEYS = {
    "model",
    "messages",
    "max_tokens",
    "max_completion_tokens",
    "tools",
    "tool_choice",
    "reasoning_effort",
}
# A client tool, which the orchestrator runs as a delegation. A server tool has a `type`.
TOOL_KEYS = {"name", "description", "input_schema"}
# A function tool, the only kind of Chat Completions tool, which the orchestrator runs.
FUNCTION_KEYS = {"name", "description", "parameters"}
DEPENDENCIES = {"data-director-sdk"}
IMPORTS = {"dd_sdk", "dd_agent_orchestrator_model", "__future__"}


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


class _Endpoint:
    """A Chat Completions endpoint that replies "Hello." and keeps each request body."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        message = {"role": "assistant", "content": "Hello."}
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 0,
                "model": "local-model",
                "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            },
        )


def _anthropic() -> tuple[Model, list[dict[str, Any]]]:
    client = _RecordingClient()
    model = AnthropicModel(
        "claude-sonnet-5-5",
        client=client,  # type: ignore[arg-type]
        effort="high",
        fallback=True,
        cache_system=True,
    )
    return model, client.requests


def _openai() -> tuple[Model, list[dict[str, Any]]]:
    import openai

    endpoint = _Endpoint()
    http_client = openai.DefaultHttpxClient(transport=httpx.MockTransport(endpoint))
    client = openai_client("http://localhost:11434/v1", None, http_client=http_client)
    model = OpenAIModel(
        "local-model", provider="localhost:11434", hosting="local", effort="low", client=client
    )
    return model, endpoint.requests


def _tools_of_anthropic(sent: dict[str, Any]) -> list[dict[str, Any]]:
    assert set(sent) <= ANTHROPIC_KEYS, f"unexpected arguments: {set(sent) - ANTHROPIC_KEYS}"
    assert sent["betas"] == [FALLBACK_BETA]
    for tool in sent["tools"]:
        assert set(tool) == TOOL_KEYS, f"{tool.get('name')} is not a client tool"
    return list(sent["tools"])


def _tools_of_openai(sent: dict[str, Any]) -> list[dict[str, Any]]:
    assert set(sent) <= OPENAI_KEYS, f"unexpected fields: {set(sent) - OPENAI_KEYS}"
    tools = []
    for tool in sent["tools"]:
        assert set(tool) == {"type", "function"} and tool["type"] == "function", tool
        assert set(tool["function"]) == FUNCTION_KEYS, f"{tool['function'].get('name')}"
        function = tool["function"]
        tools.append(
            {
                "name": function["name"],
                "description": function["description"],
                "input_schema": function["parameters"],
            }
        )
    return tools


@pytest.mark.requirement("DD-DELEGATION")
@pytest.mark.parametrize(
    ("build", "tools_of"),
    [(_anthropic, _tools_of_anthropic), (_openai, _tools_of_openai)],
    ids=["anthropic", "openai-compatible"],
)
def test_the_model_is_offered_only_delegations(runs_dir: Path, build: Any, tools_of: Any) -> None:
    model, requests = build()
    orchestrator = ModelOrchestrator(model)
    conductor = make_conductor(runs_dir, orchestrator, HelloWorld())
    # In a project no person has named, so that every tool the model can be offered is.
    conductor.projects = ProjectStore(runs_dir.parent / "projects")
    project = conductor.projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    started = conductor.projects.start_conversation(
        project, acted_for=TEST_PRINCIPAL, caused_by="test"
    )

    req = request("orchestrator.model", Message(message_text="Please greet Ada"))
    env = conductor.invoke(
        req.model_copy(update={"conversation_id": started}), acting_for=TEST_PRINCIPAL
    )

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    [sent] = requests
    tools = tools_of(sent)
    assert tools, "the manifest's agent should be offered as a tool"
    for tool in tools:
        if tool["name"] == QUESTIONS_TOOL:
            # A tool that is not a delegation: the loop ends on it and calls nothing.
            assert tool == QUESTIONS_TOOL_DEFINITION.to_json()
            continue
        if tool["name"] == NAME_TOOL:
            # Nor is this: it puts a name on the reply and calls nothing.
            assert tool == NAME_TOOL_DEFINITION.to_json()
            continue
        if tool["name"] == ENTRY_TOOL:
            # Nor this: it puts an entry point on the reply and calls nothing.
            assert tool == ENTRY_TOOL_DEFINITION.to_json()
            continue
        assert tool["description"].startswith("Ask the agent ")
    names = [t["name"] for t in tools]
    assert names.count(QUESTIONS_TOOL) == 1 and names.count(NAME_TOOL) == 1
    assert names.count(ENTRY_TOOL) == 1


@pytest.mark.requirement("DD-DELEGATION")
def test_the_package_depends_only_on_the_sdk() -> None:
    project = tomllib.loads((PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    names = {_name(d) for d in project["dependencies"]}
    assert names == DEPENDENCIES
    assert not project.get("optional-dependencies")


@pytest.mark.requirement("DD-DELEGATION")
@pytest.mark.parametrize("path", sorted(SOURCE.glob("*.py")), ids=lambda p: p.name)
def test_the_source_imports_only_the_standard_library_and_the_sdk(
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

"""The alpha chat agent against a scripted model: tools, history, and one full turn.

An alpha substantiates no requirement, so these tests carry no requirement marker.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic_ai import models
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from dd_agent_chat.agent import (
    build_agent,
    get_fairsharing_record,
    respond,
    search_fairsharing,
    to_history,
)

models.ALLOW_MODEL_REQUESTS = False


def test_search_returns_snapshot_records_with_urls():
    hits = search_fairsharing("meteorological gridded binary", limit=3)
    assert isinstance(hits, list)
    assert 0 < len(hits) <= 3
    assert all(h["url"] == f"https://fairsharing.org/{h['fairsharing_id']}" for h in hits)


def test_search_filters_by_record_type():
    hits = search_fairsharing("ontology", record_type="terminology_artefact")
    assert isinstance(hits, list)
    assert {h["record_type"] for h in hits} == {"terminology_artefact"}


def test_search_with_no_match_says_so():
    assert search_fairsharing("zzqxv") == "No FAIRsharing record in the snapshot matched."


def test_fetch_known_and_unknown_records():
    record = get_fairsharing_record("FAIRsharing.032f20")
    assert isinstance(record, dict)
    assert record["url"] == "https://fairsharing.org/FAIRsharing.032f20"
    assert "No record" in str(get_fairsharing_record("FAIRsharing.nope"))


def test_history_keeps_turns_and_drops_tool_notes():
    history = to_history(
        [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "`{}`", "metadata": {"title": "Tool: x"}},
            {"role": "assistant", "content": [{"type": "text", "text": "Hi"}]},
        ]
    )
    assert [type(m) for m in history] == [ModelRequest, ModelResponse]
    assert history[1].parts == [TextPart(content="Hi")]


def scripted(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Search once, then answer with the first record's URL."""
    returns = [
        p
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    ]
    if not returns:
        return ModelResponse(
            parts=[ToolCallPart("search_fairsharing", {"query": "meteorological", "limit": 1})]
        )
    hits = returns[0].content
    assert isinstance(hits, list)
    return ModelResponse(parts=[TextPart(f"See {hits[0]['url']}")])


def test_turn_reports_tool_calls_then_answer():
    agent = build_agent(FunctionModel(scripted))
    turn = asyncio.run(respond(agent, "Standards for weather data?", []))
    assert [c.tool_name for c in turn.tool_calls] == ["search_fairsharing"]
    assert turn.answer.startswith("See https://fairsharing.org/")


def test_default_model_needs_a_key(monkeypatch: pytest.MonkeyPatch):
    from pydantic_ai.exceptions import UserError

    monkeypatch.delenv("DD_CHAT_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(UserError):
        build_agent()

"""The alpha Data Director: one tool-using model over the FAIRsharing snapshot.

This is an alpha. It does not use the workbench, which is a development tool, so none of the
contract applies: there is no policy gate, input check, grounding linter,
evidence hashing or run record. What the model says is unchecked; the tools only make it
possible for the model to cite real FAIRsharing records rather than recall them.

The agent loop and model selection are pydantic-ai's; FAIRsharing search is R3's
`SnapshotBackend`. The model is named by a pydantic-ai model string in `DD_CHAT_MODEL`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, infer_model

from dd_agent_r3.fairsharing.records import LICENCE_NOTE
from dd_agent_r3.fairsharing.snapshot import SnapshotBackend
from dd_agent_r3.retrieve import Query, RegistryUnavailable

MODEL_ENV = "DD_CHAT_MODEL"
# Any pydantic-ai model string works, e.g. `ollama:llama3.1` (with OLLAMA_BASE_URL set).
DEFAULT_MODEL = "anthropic:claude-sonnet-5"
# Descriptions are cut to this many characters in search results; the model can fetch the rest.
DESCRIPTION_CHARS = 300
MAX_RESULTS = 20

RecordType = Literal["terminology_artefact", "model_and_format", "reporting_guideline"]

INSTRUCTIONS = f"""\
You are the Data Director, an alpha assistant that helps researchers document, publish, share
and reuse research data. You help them write metadata and data documentation, choose
metadata standards, vocabularies, ontologies and data formats, identify repositories and
persistent identifier options, and understand funder, institutional and disciplinary
requirements. You advise; the researcher decides, and your advice needs human review.

You have tools over a small offline snapshot of FAIRsharing standards records (terminology
artefacts, models and formats, and reporting guidelines). It holds no repositories or
policies and is far from complete.

- When you recommend a standard, search the snapshot first. Cite a FAIRsharing record only if
  a tool returned it, by name and URL.
- If the snapshot has nothing relevant, say so. You may then draw on general knowledge, but
  say plainly that it has not been checked against a registry.
- Ask a short clarifying question when the dataset or goal is unclear.
- Be concise. Use British English.

When you cite FAIRsharing records, end with this attribution: {LICENCE_NOTE}
"""

_backend = SnapshotBackend()


def search_fairsharing(
    query: str, record_type: RecordType | None = None, limit: int = 8
) -> list[dict[str, Any]] | str:
    """Search the FAIRsharing snapshot for standards matching the query words.

    Args:
        query: Keywords, such as a discipline, data type or standard name.
        record_type: Restrict to one kind of standard.
        limit: The number of records to return, at most 20.
    """
    try:
        hits = _backend.search(
            Query(text=query, record_type=record_type, limit=max(1, min(limit, MAX_RESULTS)))
        )
    except RegistryUnavailable as exc:
        return f"The FAIRsharing snapshot is unavailable: {exc}"
    if not hits:
        return "No FAIRsharing record in the snapshot matched."
    return [
        {
            "fairsharing_id": h.record.fairsharing_id,
            "name": h.record.name,
            "abbreviation": h.record.abbreviation,
            "record_type": h.record.record_type,
            "status": h.record.status,
            "url": h.record.url,
            "description": (h.record.description or "")[:DESCRIPTION_CHARS],
        }
        for h in hits
    ]


def get_fairsharing_record(fairsharing_id: str) -> dict[str, Any] | str:
    """Fetch one FAIRsharing record from the snapshot in full.

    Args:
        fairsharing_id: An identifier such as `FAIRsharing.032f20`, as returned by a search.
    """
    try:
        record = _backend.fetch(fairsharing_id)
    except RegistryUnavailable as exc:
        return f"The FAIRsharing snapshot is unavailable: {exc}"
    if record is None:
        return f"No record {fairsharing_id!r} in the FAIRsharing snapshot."
    return {**record.model_dump(exclude_none=True), "url": record.url}


def build_agent(model: Model | str | None = None) -> Agent[None, str]:
    """The agent. The model is resolved now, so a missing key or bad name fails at start-up."""
    resolved = infer_model(model or os.environ.get(MODEL_ENV) or DEFAULT_MODEL)
    return Agent(
        resolved,
        instructions=INSTRUCTIONS,
        tools=[search_fairsharing, get_fairsharing_record],
        name="data-director-alpha",
    )


def _text(content: Any) -> str:
    """The text of one chat message: a string, or a list of Gradio content parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_text(c) for c in content)
    if isinstance(content, dict) and content.get("type") == "text":
        return str(content.get("text", ""))
    return ""  # files and other media are not passed to the model


def to_history(messages: list[dict[str, Any]]) -> list[ModelMessage]:
    """Gradio's `{role, content}` history as pydantic-ai messages, without the tool notes."""
    history: list[ModelMessage] = []
    for message in messages:
        if message.get("metadata"):
            continue
        text = _text(message.get("content"))
        if not text:
            continue
        if message.get("role") == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=text)]))
        elif message.get("role") == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=text)]))
    return history


@dataclass(frozen=True)
class Turn:
    """What one reply produced: the tools the model called, in order, and its answer."""

    tool_calls: list[ToolCallPart]
    answer: str


async def respond(agent: Agent[None, str], message: str, history: list[dict[str, Any]]) -> Turn:
    result = await agent.run(message, message_history=to_history(history))
    calls = [
        part
        for m in result.new_messages()
        if isinstance(m, ModelResponse)
        for part in m.parts
        if isinstance(part, ToolCallPart)
    ]
    return Turn(tool_calls=calls, answer=result.output)

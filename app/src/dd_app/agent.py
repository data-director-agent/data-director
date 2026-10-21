"""The alpha Data Director: one tool-using model whose tool calls R3 through the conductor.

The model's one tool, `recommend_standards`, sends a `DatasetProfile` to R3
(`r3.standards-advisor`) through `Conductor.invoke`, so each R3 run passes the policy gate, the
input check, the grounding linter and the source check, and is stored with whom it acted for
(ADR-0018, issue #60). R3 runs in this process, registered beside the app's agent list. The
model's own turn and its final answer are not governed.

The agent loop and model selection are pydantic-ai's. The model is named by a pydantic-ai model
string in `DD_CHAT_MODEL`.
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, infer_model

from dd_agent_r3 import factory as r3
from dd_agent_r3.classes import DatasetProfile, Recommendations, TableField
from dd_agent_r3.fairsharing.records import LICENCE_NOTE
from dd_harness.conductor import Conductor
from dd_harness.settings import Settings, build_authenticator, build_conductor
from dd_sdk.contract.models import (
    Envelope,
    EvidenceItem,
    InvocationRequest,
    OutcomeStatus,
    Principal,
)

MODEL_ENV = "DD_CHAT_MODEL"
# Any pydantic-ai model string works, e.g. `ollama:llama3.1` (with OLLAMA_BASE_URL set).
DEFAULT_MODEL = "anthropic:claude-sonnet-5"
R3_AGENT_ID = "r3.standards-advisor"
TOOL_NAME = "recommend_standards"

INSTRUCTIONS = f"""\
You are the Data Director, an alpha assistant that helps researchers document, publish, share
and reuse research data. You help them write metadata and data documentation, choose
metadata standards, vocabularies, ontologies and data formats, identify repositories and
persistent identifier options, and understand funder, institutional and disciplinary
requirements. You advise; the researcher decides, and your advice needs human review.

You have one tool, `{TOOL_NAME}`. It sends a description of the dataset to a standards
advisor, which recommends controlled vocabularies, ontologies and data formats from an offline
snapshot of FAIRsharing. Each call is checked and recorded, and returns its run's
`invocation_id`. The advisor does not cover reporting guidelines, repositories or policies.

- To recommend standards, call the tool with what you know of the dataset: a title, a
  description, keywords, subject themes, media types and its fields or columns. Cite a
  FAIRsharing record only if the tool returned it, by name and URL.
- If the tool returns nothing relevant, or an outcome other than `succeeded`, say so. You may
  then draw on general knowledge, but say plainly that it has not been checked.
- Ask a short clarifying question when the dataset or goal is unclear.
- Be concise. Use British English.

When you cite FAIRsharing records, end with this attribution: {LICENCE_NOTE}
"""


@dataclass
class Governance:
    """The conductor the app's tool calls, and the principal every call acts for.

    A conductor is called on the thread that built it, one invocation at a time
    (`workbench/evaluation.py`), so both are built on one worker thread and every invocation is
    submitted to it. `create` builds them at start-up, so a bad setting stops the app before it
    serves a page.
    """

    conductor: Conductor
    acting_for: Principal
    worker: ThreadPoolExecutor = field(repr=False)

    @classmethod
    def create(cls, settings: Settings) -> Governance:
        worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dd-app")

        def build() -> tuple[Conductor, Principal]:
            # The stub authenticator: the operator's assertion until there is authentication
            # (ADR-0018, #17), not the person using the page.
            acting_for = build_authenticator(settings).principal_for(None)
            return build_conductor(settings, agents=[r3.build()]), acting_for

        try:
            conductor, acting_for = worker.submit(build).result()
        except BaseException:
            worker.shutdown()
            raise
        return cls(conductor, acting_for, worker)

    async def invoke(self, request: InvocationRequest) -> Envelope:
        future = self.worker.submit(self.conductor.invoke, request, acting_for=self.acting_for)
        return await asyncio.wrap_future(future)


def summarise(envelope: Envelope) -> dict[str, Any]:
    """What the model is told of one R3 run: its outcome and each recommendation with the
    record it is grounded on, as the evidence shows it."""
    summary: dict[str, Any] = {
        "invocation_id": envelope.invocation_id,
        "status": envelope.outcome.status.value,
        "statement": envelope.outcome.statement,
    }
    if envelope.outcome.reason_code is not None:
        summary["reason_code"] = envelope.outcome.reason_code.value
    if envelope.outcome.status is not OutcomeStatus.SUCCEEDED or envelope.payload is None:
        return summary
    evidence = {item.source_id: item for item in envelope.evidence}
    summary["recommendations"] = [
        {
            "kind": item.kind.value,
            "target": item.target,
            "rationale": item.rationale,
            "records": [
                _record(ref.source_id, evidence.get(ref.source_id)) for ref in item.grounded_on
            ],
        }
        for item in envelope.payload_as(Recommendations).items
    ]
    return summary


def _record(source_id: str, evidence: EvidenceItem | None) -> dict[str, Any]:
    """One cited record as its evidence item shows it: the content its hash covers."""
    content = (evidence.content if evidence else None) or {}
    return {
        "fairsharing_id": source_id,
        "name": content.get("name"),
        "abbreviation": content.get("abbreviation"),
        "status": content.get("status"),
        "url": evidence.source_uri if evidence else None,
    }


def build_agent(governance: Governance, model: Model | str | None = None) -> Agent[None, str]:
    """The agent. The model is resolved now, so a missing key or bad name fails at start-up."""
    resolved = infer_model(model or os.environ.get(MODEL_ENV) or DEFAULT_MODEL)

    async def recommend_standards(
        title: str | None = None,
        description: str | None = None,
        keywords: list[str] | None = None,
        themes: list[str] | None = None,
        media_types: list[str] | None = None,
        fields: list[TableField] | None = None,
    ) -> dict[str, Any]:
        """Ask the standards advisor for vocabularies, ontologies and data formats that suit a
        dataset. The run is checked and recorded.

        Args:
            title: The dataset's title.
            description: What the dataset holds and how it was made.
            keywords: Keywords, such as a discipline, data type or method.
            themes: Subject areas, such as `Soil science`.
            media_types: The files' media types, such as `text/csv`.
            fields: The dataset's columns or variables.
        """
        profile = DatasetProfile(
            title=title,
            description=description,
            keywords=keywords or [],
            themes=themes or [],
            media_types=media_types or [],
            fields=fields or [],
        )
        request = InvocationRequest(agent_id=R3_AGENT_ID, input=profile)
        return summarise(await governance.invoke(request))

    return Agent(
        resolved,
        instructions=INSTRUCTIONS,
        tools=[recommend_standards],
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
    """What one reply produced: the tools the model called, in order, the run each call
    recorded (by `tool_call_id`), and the answer."""

    tool_calls: list[ToolCallPart]
    answer: str
    runs: dict[str, str] = field(default_factory=dict)


async def respond(agent: Agent[None, str], message: str, history: list[dict[str, Any]]) -> Turn:
    result = await agent.run(message, message_history=to_history(history))
    calls = [
        part
        for m in result.new_messages()
        if isinstance(m, ModelResponse)
        for part in m.parts
        if isinstance(part, ToolCallPart)
    ]
    runs = {
        part.tool_call_id: part.content["invocation_id"]
        for m in result.new_messages()
        if isinstance(m, ModelRequest)
        for part in m.parts
        if isinstance(part, ToolReturnPart)
        and isinstance(part.content, dict)
        and "invocation_id" in part.content
    }
    return Turn(tool_calls=calls, answer=result.output, runs=runs)

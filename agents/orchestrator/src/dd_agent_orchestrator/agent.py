"""orchestrator.model: the model-backed Data Director orchestrator (ADR-0012, #21).

The Blueprint's Data Director is one agent a person converses with, which hands work to
specialist agents (§9.3, "AI Model Orchestration"). `director.stub` routes by fixed rules; this
agent lets a model decide. It has the stub's specification, `Message` in, `Reply` out, grounding
mode `delegation`, with `reply_derivation` `model` and a `chat` span for each model call.

Each run reads the harness's manifest through `ctx.delegate.manifest()` and offers the model one
tool per class each other agent accepts, so the agents it can route to are the ones the harness
has registered, never a list of its own. Delegation agents, itself included, are left out:
delegation is one level deep. A tool call is a delegation through `ctx.delegate`, so the
conductor runs the child as an ordinary governed invocation and records it on this one.

The model is sent the last `history_turns` turns of `Message.history`, oldest first, then the
current message. Every turn is still covered by the input hash; what was sent follows from the
input and the setting.

The parent succeeds once the model has replied, whatever its children's outcomes were. A failed
child is on the parent's `delegations` and its own envelope, and the reply reports it (ADR-0012,
"Discovery and failed children"). A turn the model declines, or an API failure, raises, and the
conductor records failed(agent-error): a model-derived reply is never replaced by a template.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dd_agent_orchestrator.model import Model, ModelError, ModelTurn, ToolCall
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    EvidenceItem,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Message,
    OpenInput,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    Reply,
    TurnRole,
)
from dd_sdk.delegate import Delegated, DelegationRefused
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION
from dd_sdk.process_flow import REQUIREMENTS
from dd_sdk.tracing import ATTR_MODEL_ID, chat_span, record_tokens

AGENT_ID = "orchestrator.model"
DEFAULT_HISTORY_TURNS = 20
DEFAULT_MAX_DELEGATIONS = 4
# The API's rule for a tool name.
TOOL_NAME_UNSAFE = re.compile(r"[^a-zA-Z0-9_-]")
TOOL_NAME_MAX = 64
# Keys of a generated class schema that describe the file, not the input.
SCHEMA_ANNOTATIONS = ("$comment", "$id", "$schema", "title")
CUT_SHORT = "(This reply was cut short.)"


@dataclass(frozen=True)
class Tool:
    """One tool offered to the model: delegate an input of `schema_class` to `agent_id`."""

    name: str
    agent_id: str
    schema_class: str
    definition: dict[str, Any]


def tools_from_manifest(manifest: list[dict[str, Any]], own_id: str = AGENT_ID) -> list[Tool]:
    """One tool per input class of each agent the harness lists, except delegation agents."""
    tools: list[Tool] = []
    for entry in sorted(manifest, key=lambda e: str(e.get("agent_id"))):
        agent_id = str(entry.get("agent_id"))
        if agent_id == own_id or entry.get("grounding_mode") == GroundingMode.DELEGATION.value:
            continue
        accepts = [str(name) for name in entry.get("accepts") or []]
        schemas = entry.get("schemas") or {}
        for schema_class in accepts:
            schema = (schemas.get(schema_class) or {}).get("json_schema")
            if not isinstance(schema, dict):
                continue
            base = TOOL_NAME_UNSAFE.sub("_", agent_id)
            name = base if len(accepts) == 1 else f"{base}__{schema_class}"
            description = str(entry.get("description") or agent_id)
            serves = [str(r) for r in entry.get("serves") or []]
            requirements = [r for r in serves if r in REQUIREMENTS]
            steps = [r for r in serves if r not in REQUIREMENTS]
            if requirements:
                description += f" Serves Blueprint requirement(s) {', '.join(requirements)}."
            if steps:
                description += f" Serves step(s) {', '.join(steps)}."
            tools.append(
                Tool(
                    name=name[:TOOL_NAME_MAX],
                    agent_id=agent_id,
                    schema_class=schema_class,
                    definition={
                        "name": name[:TOOL_NAME_MAX],
                        "description": (
                            f"Ask the agent {agent_id} (input class {schema_class}). {description}"
                        ),
                        "input_schema": tool_schema(schema),
                    },
                )
            )
    return tools


def tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """A class schema as a tool's input schema: without `schema_class`, which the orchestrator
    fills in, and with the integers the A2A card carried as floats made integers again."""
    out = {k: _integral(v) for k, v in schema.items() if k not in SCHEMA_ANNOTATIONS}
    properties = dict(out.get("properties") or {})
    properties.pop("schema_class", None)
    out["properties"] = properties
    out["required"] = [r for r in out.get("required") or [] if r != "schema_class"]
    return out


def _integral(value: Any) -> Any:
    # protobuf's Struct has only floating-point numbers (ADR-0027).
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: _integral(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_integral(v) for v in value]
    return value


def conversation(message: Message, history_turns: int) -> list[dict[str, Any]]:
    """The messages sent to the model: the last `history_turns` turns, then the current one.

    An agent turn becomes an assistant message. Turns before the first user turn in the window
    are dropped, since the API requires a conversation to open with the user."""
    window = list(message.history)[-history_turns:] if history_turns > 0 else []
    while window and window[0].role != TurnRole.USER:
        window.pop(0)
    messages: list[dict[str, Any]] = [
        {
            "role": "user" if turn.role == TurnRole.USER else "assistant",
            "content": turn.turn_text,
        }
        for turn in window
    ]
    messages.append({"role": "user", "content": message.message_text})
    return messages


class ModelOrchestrator:
    spec = AgentSpec(
        agent_id=AGENT_ID,
        version="0.1.0",
        description=(
            "The model-backed Data Director orchestrator. Talks with a researcher, and hands "
            "each request to the specialist agents the harness lists, through the harness."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(Message),),
        grounding_mode=GroundingMode.DELEGATION,
        payload=ClassSchema.of(Reply),
        derivations={"reply_text": Derived(Derivation.MODEL, recorded_in="reply_derivation")},
    )

    def __init__(
        self,
        model: Model,
        *,
        history_turns: int = DEFAULT_HISTORY_TURNS,
        max_delegations: int = DEFAULT_MAX_DELEGATIONS,
    ) -> None:
        self.model = model
        self.history_turns = history_turns
        self.max_delegations = max_delegations

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        message = request.input
        assert isinstance(message, Message)  # the conductor refused anything else

        if ctx.delegate is None:
            return _abstain(
                ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
                "The harness gave this run no way to delegate (for example, it was started "
                "from `workbench invoke`), so no agent was asked.",
            )
        tools = {t.name: t for t in tools_from_manifest(ctx.delegate.manifest())}
        definitions = [t.definition for t in tools.values()]
        messages = conversation(message, self.history_turns)

        delegated: list[Delegated] = []
        attempts = 0
        input_tokens = output_tokens = 0
        model_id = self.model.model_id
        while True:
            use_tools = bool(definitions) and attempts < self.max_delegations
            with chat_span(ctx.tracer, self.model.model_id) as span:
                turn = self.model.turn(messages, definitions, use_tools=use_tools)
                if turn.model_id != self.model.model_id:
                    # A server-side fallback answered.
                    span.set_attribute(ATTR_MODEL_ID, turn.model_id)
                record_tokens(span, turn.input_tokens, turn.output_tokens)
            input_tokens += turn.input_tokens
            output_tokens += turn.output_tokens
            model_id = turn.model_id
            messages.append({"role": "assistant", "content": turn.content})
            if turn.stop_reason != "tool_use" or not turn.tool_calls:
                break
            results = []
            for call in turn.tool_calls:
                attempts += 1
                results.append(self._call(call, tools, attempts, ctx, delegated))
            # Every result of one turn goes back in one message.
            messages.append({"role": "user", "content": results})

        return self._reply(turn, delegated, ctx, model_id, input_tokens, output_tokens)

    def _call(
        self,
        call: ToolCall,
        tools: dict[str, Tool],
        attempt: int,
        ctx: RunContext,
        delegated: list[Delegated],
    ) -> dict[str, Any]:
        tool = tools.get(call.name)
        if tool is None:
            return _tool_result(call, f"There is no agent behind the tool {call.name!r}.", True)
        if attempt > self.max_delegations:
            return _tool_result(
                call,
                f"Not run: this turn has reached its limit of {self.max_delegations} "
                "delegations. Reply with what you have.",
                True,
            )
        assert ctx.delegate is not None
        document = {**call.input, "schema_class": tool.schema_class}
        try:
            child = ctx.delegate(tool.agent_id, OpenInput.model_validate(document))
        except DelegationRefused as exc:
            return _tool_result(call, f"The harness did not run {tool.agent_id}: {exc}", True)
        delegated.append(child)
        envelope = child.envelope
        result = {
            "agent_id": envelope.agent_id,
            "agent_version": envelope.agent_version,
            "status": envelope.outcome.status.value,
            "reason_code": envelope.outcome.reason_code,
            "statement": envelope.outcome.statement,
            "payload": (
                envelope.payload.model_dump(mode="json", exclude_none=True)
                if envelope.payload is not None
                else None
            ),
        }
        failed = envelope.outcome.status == OutcomeStatus.FAILED
        return _tool_result(call, json.dumps(result, default=str), failed)

    def _reply(
        self,
        turn: ModelTurn,
        delegated: list[Delegated],
        ctx: RunContext,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> AgentResult:
        text = turn.text.strip()
        if turn.stop_reason == "max_tokens":
            text = f"{text}\n\n{CUT_SHORT}" if text else CUT_SHORT
        if not text:
            raise ModelError(f"the model stopped ({turn.stop_reason}) without a reply")
        if delegated:
            asked = ", ".join(
                f"{d.envelope.agent_id}@{d.envelope.agent_version} "
                f"({d.envelope.outcome.status.value})"
                for d in delegated
            )
            statement = f"Delegated to {asked}; each outcome is on its own envelope."
        else:
            statement = "Replied without delegating."
        input_ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=f"{statement} Written by {model_id}; human review is required.",
            ),
            payload=Reply(
                reply_text=text,
                reply_derivation=Derivation.MODEL,
                grounded_on=[input_ref, *(d.ref for d in delegated)],
            ),
            evidence=[
                EvidenceItem(
                    source_id=ctx.input_ref,
                    retrieved_at=datetime.now(UTC),
                    hash_algorithm=HASH_ALGORITHM,
                    canonicalisation=INPUT_CANONICALISATION,
                    content_hash=ctx.input_hash,
                ),
                *(d.evidence for d in delegated),
            ],
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


def _tool_result(call: ToolCall, content: str, is_error: bool) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": call.id,
        "content": content,
        "is_error": is_error,
    }


def _abstain(reason: ReasonCode, statement: str) -> AgentResult:
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.ABSTAINED, reason_code=reason, statement=statement)
    )

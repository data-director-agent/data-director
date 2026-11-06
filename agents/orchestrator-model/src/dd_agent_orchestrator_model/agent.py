"""orchestrator.model: the model-backed Data Director orchestrator (docs/specs/orchestration.md,
#21).

The Blueprint's Data Director is one agent a person converses with, which hands work to
specialist agents (§9.3, "AI Model Orchestration"). `orchestrator.stub` routes by fixed rules; this
agent lets a model decide. It has the stub's specification, `Message` in, `Reply` out, grounding
mode `delegation`, with `reply_derivation` `model` and a `chat` span for each model call.

Each run reads the harness's manifest through `ctx.delegate.manifest()` and offers the model one
tool per class each other agent accepts, so the agents it can route to are the ones the harness
has registered, never a list of its own. Delegation agents, itself included, are left out:
delegation is one level deep. A tool call is a delegation through `ctx.delegate`, so the
conductor runs the child as an ordinary governed invocation and records it on this one.

The model is sent the last `history_turns` turns of `Message.history`, oldest first, then the
current message. Every turn is still covered by the input hash; what was sent follows from the
input and the setting. When the conductor says the project holds an inventory
(`Message.project_inventory`, docs/specs/projects.md), the current message opens with a note of it
from the harness, so the model neither asks for one nor copies one into an agent's input.

The parent succeeds once the model has replied, whatever its children's outcomes were. A failed
child is on the parent's `delegations` and its own envelope, and the reply reports it
(docs/specs/orchestration.md, "Discovery and failed children"). A turn the model declines, or an API
failure, raises, and the conductor records failed(agent-error): a model-derived reply is never
replaced by a template.

Besides the delegations the model has one tool of the agent's own, `offer_choices`, which runs
nothing: called alone, it ends the turn, and the reply carries the question as
`Reply.reply_question` for the app to show as choices (docs/specs/orchestration.md). Called beside
a delegation, or with options that are not a valid `ChoiceQuestion`, it is answered with an error
and the loop goes on.

On a conversation's first turn (an empty `Message.history`), once the model has replied, a
`Titler` names the conversation from the researcher's message (`title.py`). The title is
`Reply.conversation_title`, declared model-derived; no title, or a failed call, leaves it out.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dd_agent_orchestrator_model.model import Model, ModelError, ModelTurn, ToolCall
from dd_agent_orchestrator_model.prompt import SYSTEM_PROMPT
from dd_agent_orchestrator_model.title import Titler, titled
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    CHOICE_OPTIONS_MAX,
    CHOICE_OPTIONS_MIN,
    ChoiceQuestion,
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
    now,
)
from dd_sdk.delegate import Delegated, DelegationRefused
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION
from dd_sdk.process_flow import requirements_of
from dd_sdk.prompts import ModelCallLog
from dd_sdk.tracing import ATTR_MODEL_ID, chat_span, record_tokens

# Who serves the model, as the agent's card names it (factory.py).
PROVIDER = "anthropic"

AGENT_ID = "orchestrator.model"
DEFAULT_HISTORY_TURNS = 20
DEFAULT_MAX_DELEGATIONS = 4
# The API's rule for a tool name.
TOOL_NAME_UNSAFE = re.compile(r"[^a-zA-Z0-9_-]")
TOOL_NAME_MAX = 64
# Keys of a generated class schema that describe the file, not the input.
SCHEMA_ANNOTATIONS = ("$comment", "$id", "$schema", "title")
CUT_SHORT = "(This reply was cut short.)"

# The one tool that is not a delegation: it asks the researcher to choose, and runs nothing.
CHOICE_TOOL = "offer_choices"
CHOICE_TOOL_DEFINITION: dict[str, Any] = {
    "name": CHOICE_TOOL,
    "description": (
        "Offer the researcher a question with a fixed set of options, shown as choices they "
        "click. It runs nothing and ends your turn: call it alone, after the text of your reply, "
        "when the answer is one of a few known options."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "question_prompt": {"type": "string", "description": "The question, in one line."},
            "question_options": {
                "type": "array",
                "minItems": CHOICE_OPTIONS_MIN,
                "maxItems": CHOICE_OPTIONS_MAX,
                "description": "The options in the order to show them; values unique.",
                "items": {
                    "type": "object",
                    "properties": {
                        "option_value": {"type": "string", "description": "A short identifier."},
                        "option_label": {
                            "type": "string",
                            "description": "What the researcher reads.",
                        },
                        "option_help": {
                            "type": "string",
                            "description": "Optional: one sentence telling this option apart.",
                        },
                    },
                    "required": ["option_value", "option_label"],
                    "additionalProperties": False,
                },
            },
            "question_multiple": {
                "type": "boolean",
                "description": "True if several options may be chosen.",
            },
            "question_other": {
                "type": "boolean",
                "description": "True if the researcher may answer in their own words instead.",
            },
        },
        "required": ["question_prompt", "question_options"],
        "additionalProperties": False,
    },
}


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
            title = str(entry.get("title") or "")
            if title:
                # The persona's name, so the reply can name who was asked (docs/specs/agents.md).
                description = f"The {title}. {description}"
            steps = [str(s) for s in entry.get("serves") or []]
            if steps:
                description += f" Serves step(s) {', '.join(steps)}."
                requirements = requirements_of(steps)
                if requirements:
                    description += f" Those steps apply {', '.join(requirements)}."
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
    # protobuf's Struct has only floating-point numbers (docs/specs/app.md).
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
    note = inventory_note(message)
    text = f"{note}\n\n{message.message_text}" if note else message.message_text
    messages.append({"role": "user", "content": text})
    return messages


def inventory_note(message: Message) -> str | None:
    """What the harness says of the project's inventory, or None if the project holds none."""
    held = message.project_inventory
    if held is None:
        return None
    files = "1 file" if held.inventory_file_count == 1 else f"{held.inventory_file_count} files"
    made = held.inventory_made_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    note = (
        "[From the harness, not the researcher] The project holds an inventory of the dataset: "
        f"{files}, made {made} by {held.inventory_tool} {held.inventory_tool_version}."
    )
    if held.inventory_limitations:
        note += " Its limitations: " + "; ".join(held.inventory_limitations) + "."
    return (
        note + " The harness puts it into the input of any agent that takes an inventory: leave "
        "`inventory` out, and send an empty input to an agent that takes only an inventory."
    )


class ModelOrchestrator:
    spec = AgentSpec(
        agent_id=AGENT_ID,
        title="Data Director",
        version="0.1.0",
        description=(
            "The model-backed Data Director orchestrator. Talks with a researcher, and hands "
            "each request to the specialist agents the harness lists, through the harness."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(Message),),
        grounding_mode=GroundingMode.DELEGATION,
        payload=ClassSchema.of(Reply),
        derivations={
            "reply_text": Derived(Derivation.MODEL, recorded_in="reply_derivation"),
            "conversation_title": Derived(Derivation.MODEL),
            "reply_question": Derived(Derivation.MODEL),
        },
    )

    def __init__(
        self,
        model: Model,
        *,
        history_turns: int = DEFAULT_HISTORY_TURNS,
        max_delegations: int = DEFAULT_MAX_DELEGATIONS,
        titler: Titler | None = None,
    ) -> None:
        self.model = model
        # Names a conversation on its first turn; None writes no title.
        self.titler = titler
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
        definitions = [*(t.definition for t in tools.values()), CHOICE_TOOL_DEFINITION]
        messages = conversation(message, self.history_turns)

        delegated: list[Delegated] = []
        attempts = 0
        input_tokens = output_tokens = 0
        model_id = self.model.model_id
        # Each call and what it sent, kept by digest with the run (docs/specs/disclosure.md).
        calls = ModelCallLog(PROVIDER)
        question: ChoiceQuestion | None = None
        while True:
            use_tools = bool(definitions) and attempts < self.max_delegations
            prompt = json.loads(
                json.dumps(
                    {
                        "system": SYSTEM_PROMPT,
                        "messages": messages,
                        "tools": definitions,
                        "tool_choice": "auto" if use_tools else "none",
                    },
                    default=str,
                )
            )
            called_at = now()
            with chat_span(ctx.tracer, self.model.model_id) as span:
                turn = self.model.turn(messages, definitions, use_tools=use_tools)
                if turn.model_id != self.model.model_id:
                    # A server-side fallback answered.
                    span.set_attribute(ATTR_MODEL_ID, turn.model_id)
                record_tokens(span, turn.input_tokens, turn.output_tokens)
            calls.record(
                prompt,
                turn.model_id,
                called_at=called_at,
                input_tokens=turn.input_tokens,
                output_tokens=turn.output_tokens,
            )
            input_tokens += turn.input_tokens
            output_tokens += turn.output_tokens
            model_id = turn.model_id
            messages.append({"role": "assistant", "content": turn.content})
            if turn.stop_reason != "tool_use" or not turn.tool_calls:
                break
            question, problem = _question_of(turn.tool_calls)
            if question is not None:
                break
            results = []
            for call in turn.tool_calls:
                if call.name == CHOICE_TOOL:
                    results.append(_tool_result(call, problem or "", True))
                    continue
                attempts += 1
                results.append(self._call(call, tools, attempts, ctx, delegated))
            # Every result of one turn goes back in one message.
            messages.append({"role": "user", "content": results})

        return self._reply(
            message, turn, question, delegated, ctx, model_id, input_tokens, output_tokens, calls
        )

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
        message: Message,
        turn: ModelTurn,
        question: ChoiceQuestion | None,
        delegated: list[Delegated],
        ctx: RunContext,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        calls: ModelCallLog,
    ) -> AgentResult:
        text = turn.text.strip()
        if question is not None and not text:
            text = question.question_prompt
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
        title = None
        if self.titler is not None and not message.history:
            title = titled(self.titler, message.message_text, ctx, calls)
            if title is not None:
                input_tokens += title.input_tokens
                output_tokens += title.output_tokens
        input_ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=f"{statement} Written by {model_id}; human review is required.",
            ),
            payload=Reply(
                reply_text=text,
                reply_derivation=Derivation.MODEL,
                conversation_title=title.text if title is not None else None,
                reply_question=question,
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
            model_calls=calls.calls,
            prompts=calls.prompts,
        )


def _question_of(calls: Sequence[ToolCall]) -> tuple[ChoiceQuestion | None, str | None]:
    """The question asked by a turn whose only tool call is `offer_choices`, or why it is not
    asked: None and None when the turn does not call the tool."""
    if not any(call.name == CHOICE_TOOL for call in calls):
        return None, None
    if len(calls) > 1:
        return None, (
            "Not shown: offer choices alone, in your final message, once the agents you need "
            "have answered."
        )
    try:
        return ChoiceQuestion.model_validate(calls[0].input), None
    except ValueError as exc:  # pydantic's ValidationError
        errors = getattr(exc, "errors", None)
        reasons = "; ".join(str(e["msg"]) for e in errors()) if callable(errors) else str(exc)
        return (
            None,
            f"Not shown: these are not valid choices ({reasons}). Fix them or ask in prose.",
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

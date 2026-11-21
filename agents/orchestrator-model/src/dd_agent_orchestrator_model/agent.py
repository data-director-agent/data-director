"""orchestrator.model: the model-backed orchestrator (docs/specs/orchestration.md, #21).

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
from the harness, so the model neither asks for one nor copies one into an agent's input; it says
too how many files the inventory it replaced listed, and another note gives the latest version of
each drafted document and whether it follows the current inventory (#1280). In a
project, a second note says which entry point the researcher chose, which steps the project log
shows started, done or skipped, and the step `suggested_next` names (docs/specs/orchestration.md):
the model keeps no place in the flow of its own, and the prompt stays the same on every run.

The parent succeeds once the model has replied, whatever its children's outcomes were. A failed
child is on the parent's `delegations` and its own envelope, and the reply reports it
(docs/specs/orchestration.md, "Discovery and failed children"). A turn the model declines, or an API
failure, raises, and the conductor records failed(agent-error): a model-derived reply is never
replaced by a template.

Besides the delegations the model has one tool of the agent's own, `ask_questions`, which runs
nothing: called alone, it ends the turn, and the reply carries the questions as
`Reply.reply_questions`, for the app to put to the researcher one at a time as form fields:
choices, or a line or more in their own words (docs/specs/orchestration.md). Called beside a
delegation, or with questions that are not valid `Question`s, it is answered with an error and the
loop goes on.

In a project no person has named (`Message.project_title_by_researcher` false), the model is
also offered `name_project`, which runs nothing either: it puts a short name for the project on
`Reply.new_project_title`, declared model-derived, which the conductor records as the project's
title unless a person names it first (docs/specs/projects.md). A note from the harness says what
the project is called, if anything, and by whom. The tool is answered and the loop goes on.
Another note says what the researcher chose and people decided (`notes.py`): the repository chosen
for deposit and each decided fact, which the model treats as settled until the researcher changes
it (#1168).

In a project whose researcher has not chosen an entry point (`Message.project_entry_by_researcher`
not true), the model is also offered `set_entry_point`, which runs nothing either: it puts the
entry point the model worked out from what the researcher said, such as data already collected,
on `Reply.new_project_entry`, declared model-derived. The conductor records it as the model's word,
which the researcher can change and which never replaces their own choice
(docs/specs/orchestration.md, invariant 18). With no entry point recorded, the harness's note names
no suggested step and tells the model to find out where the researcher is. With one recorded, from
the intake, the phase tracker or the model, the prompt tells the model not to ask again, even on
the first turn, and to suggest the step the note names (invariant 15).

On a conversation's first turn (an empty `Message.history`), once the model has replied, a
second model, the titler, names the conversation from the researcher's message (`title.py`). The
title is `Reply.conversation_title`, declared model-derived; no title, or a failed call, leaves it
out.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from dd_agent_orchestrator_model.notes import inventory_note, progress_note, record_notes
from dd_agent_orchestrator_model.own_tools import ENTRY_TOOL as ENTRY_TOOL
from dd_agent_orchestrator_model.own_tools import ENTRY_TOOL_DEFINITION as ENTRY_TOOL_DEFINITION
from dd_agent_orchestrator_model.own_tools import NAME_TOOL as NAME_TOOL
from dd_agent_orchestrator_model.own_tools import NAME_TOOL_DEFINITION as NAME_TOOL_DEFINITION
from dd_agent_orchestrator_model.own_tools import QUESTIONS_TOOL as QUESTIONS_TOOL
from dd_agent_orchestrator_model.own_tools import (
    QUESTIONS_TOOL_DEFINITION as QUESTIONS_TOOL_DEFINITION,
)
from dd_agent_orchestrator_model.own_tools import entry_of, name_of, questions_of, tool_result
from dd_agent_orchestrator_model.prompt import SYSTEM_PROMPT
from dd_agent_orchestrator_model.title import titled
from dd_sdk.agent import (
    AgentResult,
    AgentSpec,
    Derived,
    RunContext,
    abstain,
    input_evidence,
    input_ref,
)
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    GroundingMode,
    InvocationRequest,
    Message,
    OpenInput,
    Outcome,
    OutcomeStatus,
    Question,
    ReasonCode,
    Reply,
    TurnRole,
)
from dd_sdk.delegate import Delegated, DelegationRefused
from dd_sdk.model import (
    CallOptions,
    Model,
    ModelCallError,
    ModelMessage,
    ModelReply,
    ToolCall,
    ToolResult,
    ToolResults,
    ToolSpec,
    call,
)
from dd_sdk.prompts import ModelCallLog

AGENT_ID = "orchestrator.model"
# Claude Sonnet 5.5, when the provider is Anthropic and `DD_MODEL_ID` is unset (factory.py).
DEFAULT_MODEL = "claude-sonnet-5-5"
# Claude's effort when `DD_ORCHESTRATOR_EFFORT` is unset; other providers are sent none.
DEFAULT_EFFORT = "high"
# Room for a reply and the tool calls before it; a turn that reaches it is reported as cut short.
MAX_TOKENS = 16000
DEFAULT_HISTORY_TURNS = 20
DEFAULT_MAX_DELEGATIONS = 4
# The API's rule for a tool name.
TOOL_NAME_UNSAFE = re.compile(r"[^a-zA-Z0-9_-]")
TOOL_NAME_MAX = 64
# Keys of a generated class schema that describe the file, not the input.
SCHEMA_ANNOTATIONS = ("$comment", "$id", "$schema", "title")
CUT_SHORT = "(This reply was cut short.)"


class ModelError(Exception):
    """The model gave no usable turn: the provider failed, or the model declined the request."""


@dataclass(frozen=True)
class Tool:
    """One tool offered to the model: delegate an input of `schema_class` to `agent_id`."""

    name: str
    agent_id: str
    schema_class: str
    definition: ToolSpec


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
            tools.append(
                Tool(
                    name=name[:TOOL_NAME_MAX],
                    agent_id=agent_id,
                    schema_class=schema_class,
                    definition=ToolSpec(
                        name=name[:TOOL_NAME_MAX],
                        description=(
                            f"Ask the agent {agent_id} (input class {schema_class}). {description}"
                        ),
                        input_schema=tool_schema(schema),
                    ),
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


def conversation(
    message: Message, history_turns: int, manifest: Sequence[Mapping[str, Any]] = ()
) -> list[dict[str, Any]]:
    """The messages sent to the model: the last `history_turns` turns, then the current one.

    An agent turn becomes an assistant message. Turns before the first user turn in the window
    are dropped, since providers require a conversation to open with the user."""
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
    notes = [
        n
        for n in (
            inventory_note(message),
            progress_note(message, manifest),
            *record_notes(message, manifest),
        )
        if n
    ]
    text = "\n\n".join([*notes, message.message_text])
    messages.append({"role": "user", "content": text})
    return messages


@dataclass
class _Turns:
    """One run's exchange with the model: the conversation, the tools offered, the delegations
    made and attempted, the tokens spent, each call and what it sent (kept by digest with the
    run, docs/specs/disclosure.md), and what the model's own tools took."""

    messages: list[ModelMessage]
    definitions: list[ToolSpec]
    tools: dict[str, Tool]
    may_name: bool
    may_enter: bool
    calls: ModelCallLog
    delegated: list[Delegated] = field(default_factory=list)
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    questions: list[Question] | None = None
    name: str | None = None
    entry_point: int | None = None

    def answer_own(self, made: Sequence[ToolCall]) -> tuple[dict[str, ToolResult], list[ToolCall]]:
        """Answer the calls that delegate nothing (unreadable ones, a name, an entry point), and
        the readable calls left, `ask_questions` and delegations."""
        # A call whose input could not be read runs nothing, and counts against the limit, so
        # that the loop ends whatever the model sends.
        answered: dict[str, ToolResult] = {}
        for unread in (c for c in made if c.problem is not None):
            self.attempts += 1
            answered[unread.id] = tool_result(
                unread, f"Not run: {unread.problem}. Call the tool again.", is_error=True
            )
        readable = [c for c in made if c.id not in answered]
        # A name is taken whatever else the turn calls; it never ends the turn.
        for naming in (c for c in readable if c.name == NAME_TOOL):
            # A second name, or one refused, counts against the turn's limit, so that the loop
            # ends whatever the model calls.
            if self.name is not None or not self.may_name:
                self.attempts += 1
            given, result = name_of(naming, offered=self.may_name)
            self.name = given or self.name
            answered[naming.id] = result
        # So is an entry point; the last one recorded counts.
        for entering in (c for c in readable if c.name == ENTRY_TOOL):
            if self.entry_point is not None or not self.may_enter:
                self.attempts += 1
            given_entry, result = entry_of(entering, offered=self.may_enter)
            self.entry_point = given_entry or self.entry_point
            answered[entering.id] = result
        return answered, [c for c in readable if c.name not in (NAME_TOOL, ENTRY_TOOL)]


class ModelOrchestrator:
    spec = AgentSpec(
        agent_id=AGENT_ID,
        title="Data Director",
        icon="🎬",
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
            "reply_questions": Derived(Derivation.MODEL),
            "new_project_title": Derived(Derivation.MODEL),
            "new_project_entry": Derived(Derivation.MODEL),
        },
    )

    def __init__(
        self,
        model: Model,
        *,
        history_turns: int = DEFAULT_HISTORY_TURNS,
        max_delegations: int = DEFAULT_MAX_DELEGATIONS,
        titler: Model | None = None,
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
            return abstain(
                ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
                "The harness gave this run no way to delegate (for example, it was started "
                "from `workbench invoke`), so no agent was asked.",
            )
        state = self._start(message, ctx.delegate.manifest())
        while True:
            turn = self._turn(state, ctx)
            state.input_tokens += turn.usage.input_tokens or 0
            state.output_tokens += turn.usage.output_tokens or 0
            state.messages.append(turn.message)
            if turn.stop != "tool_use" or not turn.tool_calls:
                break
            results = self._results(turn, state, ctx)
            if results is None:
                break
            # Every result of one turn goes back in one message.
            state.messages.append(ToolResults(tuple(results)))

        return self._reply(message, turn, state, ctx)

    def _start(self, message: Message, manifest: list[dict[str, Any]]) -> _Turns:
        """The tools offered, from the harness's manifest, and the conversation so far."""
        tools = {t.name: t for t in tools_from_manifest(manifest)}
        definitions = [*(t.definition for t in tools.values()), QUESTIONS_TOOL_DEFINITION]
        # Only a project no person has named may be named by the model.
        may_name = message.project_title_by_researcher is False
        if may_name:
            definitions.append(NAME_TOOL_DEFINITION)
        # In a project, the model may record the entry point until the researcher chooses one.
        may_enter = (
            message.project_title_by_researcher is not None
            and message.project_entry_by_researcher is not True
        )
        if may_enter:
            definitions.append(ENTRY_TOOL_DEFINITION)
        return _Turns(
            messages=list(conversation(message, self.history_turns, manifest)),
            definitions=definitions,
            tools=tools,
            may_name=may_name,
            may_enter=may_enter,
            calls=ModelCallLog(self.model.provider),
        )

    def _results(self, turn: ModelReply, state: _Turns, ctx: RunContext) -> list[ToolResult] | None:
        """The results of a turn's tool calls, in the order made; None when the turn asks the
        researcher questions, which ends it."""
        answered, others = state.answer_own(turn.tool_calls)
        state.questions, problem = questions_of(others)
        if state.questions is not None:
            return None
        results = []
        for made in turn.tool_calls:
            if made.id in answered:
                results.append(answered[made.id])
                continue
            if made.name == QUESTIONS_TOOL:
                results.append(tool_result(made, problem or "", is_error=True))
                continue
            state.attempts += 1
            results.append(self._call(made, state.tools, state.attempts, ctx, state.delegated))
        return results

    def _turn(self, state: _Turns, ctx: RunContext) -> ModelReply:
        """One call to the model, recorded in `state.calls`, offering the tools while delegations
        remain; a provider failure or a refusal is a `ModelError`."""
        use_tools = bool(state.definitions) and state.attempts < self.max_delegations
        try:
            turn = call(
                self.model,
                ctx,
                system=SYSTEM_PROMPT,
                messages=state.messages,
                options=CallOptions(
                    MAX_TOKENS, state.calls, state.definitions, "auto" if use_tools else "none"
                ),
            )
        except ModelCallError as exc:
            raise ModelError(str(exc)) from exc
        if turn.stop == "refusal":
            raise ModelError(
                f"the model declined the request (category: {turn.refusal_category or 'none'})"
            )
        return turn

    def _call(
        self,
        call: ToolCall,
        tools: dict[str, Tool],
        attempt: int,
        ctx: RunContext,
        delegated: list[Delegated],
    ) -> ToolResult:
        tool = tools.get(call.name)
        if tool is None:
            return tool_result(
                call, f"There is no agent behind the tool {call.name!r}.", is_error=True
            )
        if attempt > self.max_delegations:
            return tool_result(
                call,
                f"Not run: this turn has reached its limit of {self.max_delegations} "
                "delegations. Reply with what you have.",
                is_error=True,
            )
        assert ctx.delegate is not None
        document = {**call.input, "schema_class": tool.schema_class}
        try:
            child = ctx.delegate(tool.agent_id, OpenInput.model_validate(document))
        except DelegationRefused as exc:
            return tool_result(
                call, f"The harness did not run {tool.agent_id}: {exc}", is_error=True
            )
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
        return tool_result(call, json.dumps(result, default=str), is_error=failed)

    def _reply(
        self, message: Message, turn: ModelReply, state: _Turns, ctx: RunContext
    ) -> AgentResult:
        questions, delegated, calls = state.questions, state.delegated, state.calls
        input_tokens, output_tokens = state.input_tokens, state.output_tokens
        text = turn.text.strip()
        if questions and not text:
            text = (
                questions[0].question_prompt
                if len(questions) == 1
                else f"I have {len(questions)} questions for you."
            )
        model_id = turn.model_id
        if turn.stop == "max_tokens":
            text = f"{text}\n\n{CUT_SHORT}" if text else CUT_SHORT
        if not text:
            raise ModelError(f"the model stopped ({turn.stop}) without a reply")
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
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=f"{statement} Written by {model_id}; human review is required.",
            ),
            payload=Reply(
                reply_text=text,
                reply_derivation=Derivation.MODEL,
                conversation_title=title.text if title is not None else None,
                reply_questions=questions,
                new_project_title=state.name,
                new_project_entry=state.entry_point,
                grounded_on=[input_ref(ctx), *(d.ref for d in delegated)],
            ),
            evidence=[
                input_evidence(ctx),
                *(d.evidence for d in delegated),
            ],
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_calls=calls.calls,
            prompts=calls.prompts,
        )

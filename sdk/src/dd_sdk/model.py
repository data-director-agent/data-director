"""One call to a language model, made the same way by every model-backed agent
(docs/specs/agents.md, Model-backed personas).

An agent calls `call` with a `Model`, the adapter for one provider. `call` does what every call
owes the run, whoever serves the model: it opens the `chat` span, records the token counts on it,
records the call and its prompt in a `ModelCallLog` (docs/specs/disclosure.md), reports a
refusal, and, when the agent gives an output schema, parses the reply against it. The adapter only
turns a `ModelRequest` into the provider's request and its response into a `ModelResponse`.

`dd_sdk.model_anthropic.AnthropicModel` is the adapter for Claude, `dd_sdk.model_openai.OpenAIModel`
the one for any OpenAI-compatible endpoint, and `dd_sdk.testing.FakeModel` the one for tests.
`dd_sdk.model_provider.configured_model` builds the adapter an agent's settings name. This module
imports no provider's SDK.

A model says who serves it and where (`provider`, `hosting`), so an agent declares what it sends
data to from the model itself (`declared`), never from a value written beside it.

**Tool calling.** An agent that lets a model call tools (the orchestrator, docs/specs/
orchestration.md) offers them as `ToolSpec`s and keeps the conversation in this module's types,
never one provider's: the model's turn is an `AssistantMessage` with its `ToolCall`s, and the
agent answers with one `ToolResults` message. Each adapter translates them to and from its
provider's format. Content a provider requires back as it was sent (Claude's thinking blocks, the
signatures some OpenAI-compatible servers put on a tool call) travels in `AssistantMessage.replay`,
which only an adapter for the same provider reads. The call's record holds the neutral form.

A provider's failure to answer (an error status, no connection) is a `ModelCallError`, so an agent
need not import the provider's package to handle it.

While an agent runs, `dd_sdk.serve` binds the model grant the conductor sent to the run
(`bind_grant`), and every client the SDK builds sends it to the model broker with each call
(`current_grant`, docs/specs/model-accounts.md). An agent's own code never handles the grant, so a
client that is not given the run context still sends the right one.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol, overload

from pydantic import BaseModel, ValidationError

from dd_sdk.agent import ModelUse, RunContext
from dd_sdk.contract.models import now
from dd_sdk.model_account import record_account
from dd_sdk.prompts import ModelCallLog
from dd_sdk.tracing import ATTR_MODEL_ID, chat_span, record_tokens

# The most a reply may run to, in tokens, unless the agent says otherwise.
DEFAULT_MAX_TOKENS = 4096

# The model grant of the run in progress in this context, if the conductor sent one.
_GRANT: ContextVar[str | None] = ContextVar("dd_model_grant", default=None)


@contextmanager
def bind_grant(grant: str | None) -> Iterator[None]:
    """Make `grant` the current run's model grant until the block ends."""
    token = _GRANT.set(grant)
    try:
        yield
    finally:
        _GRANT.reset(token)


def current_grant() -> str | None:
    """The model grant of the run in progress, or None outside a run or when none was sent."""
    return _GRANT.get()


@dataclass(frozen=True)
class Usage:
    """The tokens one call used, where the provider reports them."""

    input_tokens: int | None = None
    output_tokens: int | None = None


# Why a model stopped: it finished, it called tools, it ran out of room, or it declined.
type StopReason = Literal["end_turn", "tool_use", "max_tokens", "refusal"]
# Whether the model may call the tools it is offered on this call.
type ToolChoice = Literal["auto", "none"]


class ModelCallError(Exception):
    """The provider did not answer: it returned an error status, or could not be reached. The
    message names the status or the failure, never a key."""


@dataclass(frozen=True)
class ToolSpec:
    """A tool the model is offered: its name, what it does, and the JSON Schema of its input."""

    name: str
    description: str
    input_schema: Mapping[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": dict(self.input_schema),
        }


@dataclass(frozen=True)
class ToolCall:
    """One call the model made. `problem` says why its input could not be read, if it could not
    (an OpenAI-compatible server sends the input as text, which may not be a JSON object); the
    agent answers such a call with an error rather than running it."""

    id: str
    name: str
    input: Mapping[str, Any]
    problem: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "name": self.name, "input": dict(self.input)}
        if self.problem is not None:
            out["problem"] = self.problem
        return out


@dataclass(frozen=True)
class ToolResult:
    """The agent's answer to one `ToolCall`."""

    call_id: str
    content: str
    is_error: bool = False

    def to_json(self) -> dict[str, Any]:
        return {"call_id": self.call_id, "content": self.content, "is_error": self.is_error}


@dataclass(frozen=True)
class Replay:
    """A provider's own form of an assistant message, to be sent back to that provider as it
    was returned."""

    provider: str
    content: Any


@dataclass(frozen=True)
class AssistantMessage:
    """The model's turn, to append to the conversation before the next call."""

    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    replay: Replay | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"role": "assistant", "content": self.text}
        if self.tool_calls:
            out["tool_calls"] = [c.to_json() for c in self.tool_calls]
        return out


@dataclass(frozen=True)
class ToolResults:
    """The agent's answers to every tool call of one turn, sent back together."""

    results: tuple[ToolResult, ...]

    def to_json(self) -> dict[str, Any]:
        return {"role": "tool", "results": [r.to_json() for r in self.results]}


# One message of a conversation: a text message (`{"role": "user" | "assistant", "content": str}`),
# the model's turn, or the agent's answers to its tool calls.
type ModelMessage = Mapping[str, Any] | AssistantMessage | ToolResults


def message_json(message: ModelMessage) -> dict[str, Any]:
    """`message` as JSON, as the call's record keeps it."""
    if isinstance(message, (AssistantMessage, ToolResults)):
        return message.to_json()
    return dict(message)


@dataclass(frozen=True)
class ModelRequest:
    """What an adapter is asked to send: the system prompt, the messages, the class the reply
    must be an instance of, if the agent gave one, and the tools the model is offered, if any."""

    system: str
    messages: tuple[ModelMessage, ...]
    schema: type[BaseModel] | None = None
    max_tokens: int = DEFAULT_MAX_TOKENS
    tools: tuple[ToolSpec, ...] = ()
    tool_choice: ToolChoice = "auto"


@dataclass(frozen=True)
class ModelResponse:
    """What an adapter returns: the reply's text, whether the model declined, the model the
    response names (if it names one) and the tokens used; with tools, the calls the model made,
    why it stopped, and its own form of the turn to send back (`replay`). `refusal_category` is
    the provider's reason for declining, if it gives one."""

    text: str
    refused: bool = False
    model_id: str | None = None
    usage: Usage = Usage()
    tool_calls: tuple[ToolCall, ...] = ()
    stop: StopReason = "end_turn"
    replay: Replay | None = None
    refusal_category: str | None = None


class Model(Protocol):
    """The adapter for one provider and one model. `provider` is who serves the model, as the
    agent's card names it (`dd_sdk.agent.ModelUse`); `model_id` the model asked for; `hosting`
    whether it runs on the provider's service or on the institution's own
    (docs/specs/policy-and-identity.md)."""

    provider: str
    model_id: str
    hosting: Literal["hosted", "local"]

    def send(self, request: ModelRequest) -> ModelResponse: ...


def declared(model: Model) -> ModelUse:
    """What an agent's card declares about `model`: the provider, the model and the hosting."""
    return ModelUse(model.provider, model.model_id, model.hosting)


@dataclass(frozen=True)
class ModelReply[T: BaseModel = BaseModel]:
    """One call's result. `parsed` is the reply as an instance of the schema, if one was given
    and the model did not decline; `model_id` is the model the response named, or the one asked
    for; `calls` holds the call and what was sent. `tool_calls` and `stop` say what the model
    called and why it stopped, and `message` is its turn, to append to the conversation."""

    text: str
    parsed: T | None
    refused: bool
    model_id: str
    usage: Usage
    calls: ModelCallLog
    tool_calls: tuple[ToolCall, ...] = ()
    stop: StopReason = "end_turn"
    message: AssistantMessage = AssistantMessage("")
    refusal_category: str | None = None


class ModelOutputError(ValueError):
    """The model's reply is not an instance of the schema it was given. `reply` keeps the reply,
    which the call has already recorded, so the agent can say what was not used and why."""

    def __init__(self, message: str, reply: ModelReply[Any]) -> None:
        super().__init__(message)
        self.reply = reply


@overload
def call(
    model: Model,
    ctx: RunContext,
    *,
    system: str,
    messages: Sequence[ModelMessage],
    schema: None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    calls: ModelCallLog | None = None,
    tools: Sequence[ToolSpec] = (),
    tool_choice: ToolChoice = "auto",
) -> ModelReply: ...


@overload
def call[T: BaseModel](
    model: Model,
    ctx: RunContext,
    *,
    system: str,
    messages: Sequence[ModelMessage],
    schema: type[T],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    calls: ModelCallLog | None = None,
    tools: Sequence[ToolSpec] = (),
    tool_choice: ToolChoice = "auto",
) -> ModelReply[T]: ...


def call[T: BaseModel](
    model: Model,
    ctx: RunContext,
    *,
    system: str,
    messages: Sequence[ModelMessage],
    schema: type[T] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    calls: ModelCallLog | None = None,
    tools: Sequence[ToolSpec] = (),
    tool_choice: ToolChoice = "auto",
) -> ModelReply[T]:
    """Make one model call and record it.

    The call is recorded in `calls` if given, so a run that calls a model more than once keeps
    one log, or else in a new log for `model.provider`. `tools` are offered to the model, which
    may call them unless `tool_choice` is `none`. Raises `ModelOutputError` if a `schema` was
    given and the reply is not an instance of it, and `ModelCallError` (from the adapter) if the
    provider did not answer, after the span has recorded it.
    """
    request = ModelRequest(system, tuple(messages), schema, max_tokens, tuple(tools), tool_choice)
    # What is sent, kept by digest with the run (docs/specs/disclosure.md), in the neutral form.
    # Sampling parameters and the schema are not part of the prompt; the tools are.
    sent: dict[str, Any] = {
        "system": system,
        "messages": [message_json(m) for m in request.messages],
    }
    if request.tools:
        sent["tools"] = [t.to_json() for t in request.tools]
        sent["tool_choice"] = tool_choice
    log = calls if calls is not None else ModelCallLog(model.provider)
    with chat_span(ctx.tracer, model.model_id) as span:
        called_at = now()
        response = model.send(request)
        usage = response.usage
        record_tokens(span, usage.input_tokens, usage.output_tokens)
        # The model the response names, which may be more exact than the one asked for.
        model_id = response.model_id or model.model_id
        span.set_attribute(ATTR_MODEL_ID, model_id)
        # Whose account paid, as the broker said (docs/specs/model-accounts.md).
        account = record_account(span)
    log.record(
        sent,
        model_id,
        called_at=called_at,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        account=account,
    )
    stop: StopReason = "refusal" if response.refused else response.stop
    reply: ModelReply[T] = ModelReply(
        response.text,
        None,
        response.refused,
        model_id,
        usage,
        log,
        tool_calls=response.tool_calls,
        stop=stop,
        message=AssistantMessage(response.text, response.tool_calls, response.replay),
        refusal_category=response.refusal_category,
    )
    if schema is None or response.refused:
        return reply
    try:
        parsed = schema.model_validate_json(response.text)
    except ValidationError as error:
        raise ModelOutputError(
            f"the reply is not a {schema.__name__}: {error.error_count()} error(s)", reply
        ) from error
    return replace(reply, parsed=parsed)

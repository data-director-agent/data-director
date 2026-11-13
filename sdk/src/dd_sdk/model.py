"""One call to a language model, made the same way by every model-backed agent
(docs/specs/agents.md, Model-backed personas).

An agent calls `call` with a `Model`, the adapter for one provider. `call` does what every call
owes the run, whoever serves the model: it opens the `chat` span, records the token counts on it,
records the call and its prompt in a `ModelCallLog` (docs/specs/disclosure.md), reports a
refusal, and, when the agent gives an output schema, parses the reply against it. The adapter only
turns a `ModelRequest` into the provider's request and its response into a `ModelResponse`.

`dd_sdk.model_anthropic.AnthropicModel` is the adapter for Claude, and `dd_sdk.testing.FakeModel`
the one for tests. This module imports no provider's SDK.

While an agent runs, `dd_sdk.serve` binds the model grant the conductor sent to the run
(`bind_grant`), and every client the SDK builds sends it to the model broker with each call
(`current_grant`, docs/specs/model-accounts.md). An agent's own code never handles the grant, so a
client that is not given the run context still sends the right one.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Protocol, overload

from pydantic import BaseModel, ValidationError

from dd_sdk.agent import RunContext
from dd_sdk.contract.models import now
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


@dataclass(frozen=True)
class ModelRequest:
    """What an adapter is asked to send: the system prompt, the messages, and the class the reply
    must be an instance of, if the agent gave one."""

    system: str
    messages: tuple[Mapping[str, Any], ...]
    schema: type[BaseModel] | None = None
    max_tokens: int = DEFAULT_MAX_TOKENS


@dataclass(frozen=True)
class ModelResponse:
    """What an adapter returns: the reply's text, whether the model declined, the model the
    response names (if it names one) and the tokens used."""

    text: str
    refused: bool = False
    model_id: str | None = None
    usage: Usage = Usage()


class Model(Protocol):
    """The adapter for one provider and one model. `provider` is who serves the model, as the
    agent's card names it (`dd_sdk.agent.ModelUse`); `model_id` the model asked for."""

    provider: str
    model_id: str

    def send(self, request: ModelRequest) -> ModelResponse: ...


@dataclass(frozen=True)
class ModelReply[T: BaseModel = BaseModel]:
    """One call's result. `parsed` is the reply as an instance of the schema, if one was given
    and the model did not decline; `model_id` is the model the response named, or the one asked
    for; `calls` holds the call and what was sent."""

    text: str
    parsed: T | None
    refused: bool
    model_id: str
    usage: Usage
    calls: ModelCallLog


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
    messages: Sequence[Mapping[str, Any]],
    schema: None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    calls: ModelCallLog | None = None,
) -> ModelReply: ...


@overload
def call[T: BaseModel](
    model: Model,
    ctx: RunContext,
    *,
    system: str,
    messages: Sequence[Mapping[str, Any]],
    schema: type[T],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    calls: ModelCallLog | None = None,
) -> ModelReply[T]: ...


def call[T: BaseModel](
    model: Model,
    ctx: RunContext,
    *,
    system: str,
    messages: Sequence[Mapping[str, Any]],
    schema: type[T] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    calls: ModelCallLog | None = None,
) -> ModelReply[T]:
    """Make one model call and record it.

    The call is recorded in `calls` if given, so a run that calls a model more than once keeps
    one log, or else in a new log for `model.provider`. Raises `ModelOutputError` if a `schema`
    was given and the reply is not an instance of it; whatever the provider's client raises
    propagates, after the span has recorded it.
    """
    request = ModelRequest(system, tuple(messages), schema, max_tokens)
    # What is sent, kept by digest with the run (docs/specs/disclosure.md). Sampling parameters
    # and the schema are not part of the prompt.
    sent = {"system": system, "messages": [dict(m) for m in request.messages]}
    log = calls if calls is not None else ModelCallLog(model.provider)
    with chat_span(ctx.tracer, model.model_id) as span:
        called_at = now()
        response = model.send(request)
        usage = response.usage
        record_tokens(span, usage.input_tokens, usage.output_tokens)
        # The model the response names, which may be more exact than the one asked for.
        model_id = response.model_id or model.model_id
        span.set_attribute(ATTR_MODEL_ID, model_id)
    log.record(
        sent,
        model_id,
        called_at=called_at,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )
    reply: ModelReply[T] = ModelReply(response.text, None, response.refused, model_id, usage, log)
    if schema is None or response.refused:
        return reply
    try:
        parsed = schema.model_validate_json(response.text)
    except ValidationError as error:
        raise ModelOutputError(
            f"the reply is not a {schema.__name__}: {error.error_count()} error(s)", reply
        ) from error
    return ModelReply(response.text, parsed, False, model_id, usage, log)

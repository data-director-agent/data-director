"""The `dd_sdk.model` adapter for Claude, through the Messages API.

This is the SDK's only importer of the `anthropic` package, which is the SDK's optional
`anthropic` extra (docs/specs/dependencies.md). The import is made when an `AnthropicModel` is
built without a client, or is asked for structured output, so the SDK imports without it.

The key is always passed explicitly (`dd_sdk.credentials.api_key`), so the `anthropic` package's
own credential chain is never used (docs/specs/policy-and-identity.md).

`anthropic_client(endpoint)` builds the client every Claude-calling agent uses, whether through
`AnthropicModel` or its own code. Given the model broker's endpoint (`dd_sdk.credentials.
model_endpoint`), the client sends the agent's broker credential where it would send a key, and
the current run's model grant (`dd_sdk.model.current_grant`) as `X-DD-Model-Grant` with each call
(docs/specs/model-accounts.md). It reads whose account paid from each answer
(`dd_sdk.model_account.report`), so the call's record says so.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from dd_sdk import model_account
from dd_sdk.credentials import ModelEndpoint
from dd_sdk.model import (
    AssistantMessage,
    ModelCallError,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    Replay,
    StopReason,
    ToolCall,
    ToolResults,
    Usage,
    current_grant,
)
from dd_sdk.model_grant import HEADER_GRANT

if TYPE_CHECKING:
    import anthropic

# Who serves the model, as an agent's card names it (`dd_sdk.agent.ModelUse`).
PROVIDER = "anthropic"
# The efforts Claude accepts (`output_config.effort`).
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# The beta that lets the API route a declined request to another model (`fallbacks`).
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def anthropic_client(endpoint: ModelEndpoint, *, http_client: Any = None) -> anthropic.Anthropic:
    """A Messages API client for `endpoint`. Through the broker, every request carries the current
    run's model grant, and every answer says whose account paid. `http_client` replaces the
    client's own HTTP client, for tests."""
    import anthropic as _anthropic

    options: dict[str, Any] = {"api_key": endpoint.api_key, "base_url": endpoint.base_url}
    if http_client is not None:
        options["http_client"] = http_client
    if not endpoint.brokered:
        return _anthropic.Anthropic(**options)

    # The hook runs in the thread and context that made the call, so the call's record reads it.
    def payer(response: Any) -> None:
        model_account.report(response.headers)

    if http_client is None:
        http_client = _anthropic.DefaultHttpxClient()
    http_client.event_hooks["response"] = [*http_client.event_hooks["response"], payer]
    options["http_client"] = http_client

    class Brokered(_anthropic.Anthropic):
        # The client reads its default headers afresh for every request, so the grant is the one
        # bound to the run that makes the call.
        @property
        def default_headers(self) -> dict[str, Any]:
            headers = dict(super().default_headers)
            grant = current_grant()
            if grant is not None:
                headers[HEADER_GRANT] = grant
            return headers

    return Brokered(**options)


def _error(exc: Exception) -> ModelCallError | None:
    """`exc` as a `ModelCallError` if it is the client's failure to get an answer."""
    try:
        import anthropic as _anthropic
    except ImportError:  # pragma: no cover - a client was given without the package
        return None
    if isinstance(exc, _anthropic.APIStatusError):
        return ModelCallError(f"the Messages API answered {exc.status_code}: {exc.message}")
    if isinstance(exc, _anthropic.APIConnectionError):
        return ModelCallError(f"the Messages API could not be reached: {exc}")
    return None


def _messages(messages: Sequence[ModelMessage]) -> list[dict[str, Any]]:
    """The conversation in the Messages API's format."""
    out: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, AssistantMessage):
            if message.replay is not None and message.replay.provider == PROVIDER:
                # Thinking blocks go back as they came.
                content = [dict(block) for block in message.replay.content]
            else:
                content = [{"type": "text", "text": message.text}] if message.text else []
                content += [
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": dict(c.input)}
                    for c in message.tool_calls
                ]
            out.append({"role": "assistant", "content": content})
        elif isinstance(message, ToolResults):
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": r.call_id,
                            "content": r.content,
                            "is_error": r.is_error,
                        }
                        for r in message.results
                    ],
                }
            )
        else:
            out.append(dict(message))
    return out


_STOPS: dict[str, StopReason] = {
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
    "refusal": "refusal",
}


@dataclass(frozen=True)
class ToolLoopOptions:
    """What an agent with a long tool loop (the orchestrator) asks of Claude: an `effort`
    (`EFFORTS`), `fallback`, which lets the API route a declined request to another model by
    the refusal's category, and `cache_system`, which caches the fixed system prompt across
    calls. The defaults ask for none of them: the request is the plain Messages API call."""

    effort: str | None = None
    fallback: bool = False
    cache_system: bool = False


class AnthropicModel:
    """Claude, by model id. Give a `client` (tests), an `endpoint`
    (`dd_sdk.credentials.model_endpoint`) or an `api_key`.

    An agent with a long tool loop asks for more through `options` (`ToolLoopOptions`).
    `tool_use` says the agent relies on the model to call tools, which its card declares
    (`dd_sdk.model.declared`)."""

    provider = PROVIDER
    # Claude is served by Anthropic, or by the gateway the broker forwards to on its behalf.
    hosting: Literal["hosted", "local"] = "hosted"

    def __init__(
        self,
        model_id: str,
        *,
        api_key: str | None = None,
        endpoint: ModelEndpoint | None = None,
        client: anthropic.Anthropic | None = None,
        options: ToolLoopOptions | None = None,
        tool_use: bool = False,
    ) -> None:
        if client is None:
            if endpoint is None:
                if not api_key:
                    raise ValueError("AnthropicModel needs a client, an endpoint or an api_key")
                endpoint = ModelEndpoint(api_key)
            client = anthropic_client(endpoint)
        self._client = client
        self.model_id = model_id
        options = options or ToolLoopOptions()
        self.effort = options.effort
        self.fallback = options.fallback
        self.cache_system = options.cache_system
        self.tool_use = tool_use

    def send(self, request: ModelRequest) -> ModelResponse:
        system: Any = request.system
        if self.cache_system:
            system = [
                {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
            ]
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": request.max_tokens,
            "system": system,
            "messages": _messages(request.messages),
        }
        if request.tools:
            kwargs["tools"] = [t.to_json() for t in request.tools]
            kwargs["tool_choice"] = {"type": request.tool_choice}
        output_config: dict[str, Any] = {}
        if self.effort is not None:
            output_config["effort"] = self.effort
        if request.schema is not None:
            import anthropic as _anthropic

            # Structured output: the reply is constrained to the schema, adapted to what the
            # API accepts (closed objects, supported keywords).
            output_config["format"] = {
                "type": "json_schema",
                "schema": _anthropic.transform_schema(request.schema),
            }
        if output_config:
            kwargs["output_config"] = output_config
        try:
            if self.fallback:
                response = self._client.beta.messages.create(
                    **kwargs, betas=[FALLBACK_BETA], fallbacks="default"
                )
            else:
                response = self._client.messages.create(**kwargs)
        except Exception as exc:
            if (error := _error(exc)) is not None:
                raise error from exc
            raise
        usage = getattr(response, "usage", None)
        content = list(response.content)
        tool_calls = tuple(
            ToolCall(b.id, b.name, dict(b.input)) for b in content if b.type == "tool_use"
        )
        details = getattr(response, "stop_details", None)
        return ModelResponse(
            text="".join(block.text for block in content if block.type == "text"),
            refused=response.stop_reason == "refusal",
            model_id=getattr(response, "model", None),
            usage=Usage(_input_tokens(usage), getattr(usage, "output_tokens", None)),
            tool_calls=tool_calls,
            stop=_STOPS.get(str(response.stop_reason), "end_turn"),
            replay=(
                Replay(
                    PROVIDER,
                    tuple(
                        b.model_dump(mode="json", by_alias=True, exclude_none=True) for b in content
                    ),
                )
                if request.tools
                else None
            ),
            refusal_category=getattr(details, "category", None) if details else None,
        )


def _input_tokens(usage: Any) -> int | None:
    """The input the model read, cached input included."""
    tokens = getattr(usage, "input_tokens", None)
    if tokens is None:
        return None
    cached = (getattr(usage, "cache_read_input_tokens", None) or 0) + (
        getattr(usage, "cache_creation_input_tokens", None) or 0
    )
    return int(tokens) + cached

"""The `dd_sdk.model` adapter for any endpoint that speaks the OpenAI-compatible Chat Completions
API: OpenAI itself, Gemini through Google's compatibility endpoint, a local server (Ollama, vLLM,
llama.cpp, LM Studio) or a gateway such as LiteLLM.

This is the SDK's only importer of the `openai` package, which is the SDK's optional `openai`
extra (docs/specs/dependencies.md). The import is made when an `OpenAIModel` is built without a
client, so the SDK imports without it.

Only the key and base URL the agent was configured with reach the endpoint
(docs/specs/policy-and-identity.md). The `openai` package also reads `OPENAI_API_KEY`,
`OPENAI_BASE_URL`, `OPENAI_ORG_ID`, `OPENAI_PROJECT_ID` and `OPENAI_CUSTOM_HEADERS` from the process
environment, and the last can replace the key it was given. So the client is given the key and
base URL explicitly, and a request hook (`_only_ours`) sends only the headers the client sets for
itself, with the agent's own key as the bearer token, or with no `Authorization` header at all for
a local endpoint that needs no key.

Through the model broker (docs/specs/model-accounts.md), the base URL is the broker's
`/{provider}` and the key is the agent's broker credential. The same hook then adds the current
run's model grant (`dd_sdk.model.current_grant`) as `X-DD-Model-Grant`, and a response hook reads
whose account paid from each answer (`dd_sdk.model_account.report`), so the call's record says so.

`dd_sdk.model_provider.configured_model` builds this adapter from an agent's settings.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from dd_sdk import model_account
from dd_sdk.model import (
    AssistantMessage,
    ModelCallError,
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
    import openai

# The headers the client sets for itself, which carry nothing taken from the environment. Every
# other header is dropped before a request is sent.
_OWN_HEADERS = frozenset(
    {
        "accept",
        "accept-encoding",
        "connection",
        "content-length",
        "content-type",
        "host",
        "user-agent",
    }
)
# The client's own platform and retry headers.
_OWN_PREFIX = "x-stainless-"


def _only_ours(api_key: str | None, *, brokered: bool = False) -> Callable[[Any], None]:
    """A request hook that keeps the client's own headers and sets `api_key` as the bearer token,
    or none when there is no key. Through the broker it also sets the run's model grant."""

    def hook(request: Any) -> None:
        for name in list(request.headers):
            lowered = name.lower()
            if lowered not in _OWN_HEADERS and not lowered.startswith(_OWN_PREFIX):
                del request.headers[name]
        if api_key:
            request.headers["Authorization"] = f"Bearer {api_key}"
        if brokered and (grant := current_grant()) is not None:
            # The hook runs for every request, so the grant is the one bound to the run that makes
            # the call.
            request.headers[HEADER_GRANT] = grant

    return hook


def _payer(response: Any) -> None:
    """A response hook that records whose account paid, in the thread and context that made the
    call, so the call's record reads it."""
    model_account.report(response.headers)


def openai_client(
    base_url: str, api_key: str | None, *, brokered: bool = False, http_client: Any = None
) -> openai.OpenAI:
    """A Chat Completions client for `base_url` that sends `api_key`, or no key, and nothing it
    finds in the environment. `brokered` is for the model broker: `api_key` is then the agent's
    broker credential. `http_client` replaces the client's own HTTP client, for tests."""
    import openai as _openai

    if http_client is None:
        http_client = _openai.DefaultHttpxClient()
    http_client.event_hooks["request"] = [
        *http_client.event_hooks["request"],
        _only_ours(api_key, brokered=brokered),
    ]
    if brokered:
        http_client.event_hooks["response"] = [*http_client.event_hooks["response"], _payer]
    return _openai.OpenAI(
        # The client insists on a key; with none, the hook sends no Authorization header.
        api_key=api_key or "unused",
        base_url=base_url,
        http_client=http_client,
    )


# Why the model stopped, by the response's `finish_reason`.
_STOPS: dict[str, StopReason] = {
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}
# The efforts the Chat Completions API names (`reasoning_effort`).
EFFORTS = ("low", "medium", "high")


def _error(exc: Exception) -> ModelCallError | None:
    """`exc` as a `ModelCallError` if it is the client's failure to get an answer."""
    try:
        import openai as _openai
    except ImportError:  # pragma: no cover - a client was given without the package
        return None
    if isinstance(exc, _openai.APIStatusError):
        return ModelCallError(f"the endpoint answered {exc.status_code}: {exc.message}")
    if isinstance(exc, _openai.APIConnectionError):
        return ModelCallError(f"the endpoint could not be reached: {exc}")
    return None


def _assistant(message: AssistantMessage) -> dict[str, Any]:
    """The model's turn rebuilt in the Chat Completions format."""
    out: dict[str, Any] = {"role": "assistant", "content": message.text or None}
    if message.tool_calls:
        out["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": json.dumps(dict(c.input))},
            }
            for c in message.tool_calls
        ]
    elif out["content"] is None:
        out["content"] = ""
    return out


def _tool_call(call: Any) -> tuple[ToolCall, dict[str, Any]]:
    """One tool call of a response, and the call as it goes back, its arguments as sent and any
    field the server added (such as a signature it requires back) kept."""
    function = call.function
    arguments = function.arguments or ""
    back: dict[str, Any] = {
        **(getattr(call, "model_extra", None) or {}),
        "id": call.id,
        "type": "function",
        "function": {"name": function.name, "arguments": arguments},
    }
    try:
        given = json.loads(arguments) if arguments.strip() else {}
    except ValueError:
        given = None
    if not isinstance(given, dict):
        return ToolCall(call.id, function.name, {}, "the arguments are not a JSON object"), back
    return ToolCall(call.id, function.name, given), back


class OpenAIModel:
    """A model behind an OpenAI-compatible endpoint. Give a `client` (tests) or a `base_url`, and
    the `api_key` if the endpoint needs one.

    `provider` and `hosting` are what the agent's card declares (`dd_sdk.model.declared`).
    `max_tokens_field` is the request field that caps the reply: OpenAI's own API wants
    `max_completion_tokens`, and most other servers `max_tokens`. `effort`, if given, is sent as
    `reasoning_effort` (`EFFORTS`). `brokered` says that `base_url` is the model broker and
    `api_key` the agent's broker credential (`openai_client`). `tool_use` says the agent relies on
    the model to call tools, which its card declares."""

    def __init__(  # noqa: PLR0913
        self,
        model_id: str,
        *,
        provider: str,
        hosting: Literal["hosted", "local"],
        base_url: str | None = None,
        api_key: str | None = None,
        max_tokens_field: str = "max_tokens",
        effort: str | None = None,
        brokered: bool = False,
        client: openai.OpenAI | None = None,
        tool_use: bool = False,
    ) -> None:
        if client is None:
            if base_url is None:
                raise ValueError("OpenAIModel needs a client or a base_url")
            client = openai_client(base_url, api_key, brokered=brokered)
        self._client = client
        self.model_id = model_id
        self.provider = provider
        self.hosting: Literal["hosted", "local"] = hosting
        self.effort = effort
        self._max_tokens_field = max_tokens_field
        self.tool_use = tool_use

    def _messages(self, request: ModelRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": request.system}]
        for sent in request.messages:
            if isinstance(sent, AssistantMessage):
                if sent.replay is not None and sent.replay.provider == self.provider:
                    messages.append(dict(sent.replay.content))
                else:
                    messages.append(_assistant(sent))
            elif isinstance(sent, ToolResults):
                # The format has no error flag, so an error says so in its content.
                messages.extend(
                    {
                        "role": "tool",
                        "tool_call_id": r.call_id,
                        "content": f"Error: {r.content}" if r.is_error else r.content,
                    }
                    for r in sent.results
                )
            else:
                if not isinstance(sent.get("content"), str):
                    raise TypeError("OpenAIModel sends text messages, tool calls and results only")
                messages.append(dict(sent))
        return messages

    def send(self, request: ModelRequest) -> ModelResponse:
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "messages": self._messages(request),
            self._max_tokens_field: request.max_tokens,
        }
        if request.tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": dict(t.input_schema),
                    },
                }
                for t in request.tools
            ]
            kwargs["tool_choice"] = request.tool_choice
        if self.effort is not None:
            kwargs["reasoning_effort"] = self.effort
        if request.schema is not None:
            from openai.lib import type_to_response_format_param

            # Structured output: the reply is constrained to the class as a strict JSON schema.
            # `dd_sdk.model.call` parses the text, so a reply that is not an instance is recorded
            # before it is refused.
            kwargs["response_format"] = type_to_response_format_param(request.schema)
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            if (error := _error(exc)) is not None:
                raise error from exc
            raise
        choice = response.choices[0] if response.choices else None
        reply = choice.message if choice else None
        usage = getattr(response, "usage", None)
        text = (reply.content or "") if reply else ""
        parsed = [_tool_call(c) for c in (getattr(reply, "tool_calls", None) or [])]
        tool_calls = tuple(call for call, _ in parsed)
        refused = bool(reply and getattr(reply, "refusal", None))
        stop = _STOPS.get(str(getattr(choice, "finish_reason", None)), "end_turn")
        if tool_calls and stop == "end_turn":
            # Some servers end a turn of tool calls with `stop`.
            stop = "tool_use"
        replay = None
        if request.tools:
            back: dict[str, Any] = {"role": "assistant", "content": text or None}
            if parsed:
                back["tool_calls"] = [b for _, b in parsed]
            elif back["content"] is None:
                back["content"] = ""
            replay = Replay(self.provider, back)
        return ModelResponse(
            text=text,
            refused=refused or stop == "refusal",
            model_id=getattr(response, "model", None) or None,
            usage=Usage(
                getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)
            ),
            tool_calls=tool_calls,
            stop="refusal" if refused else stop,
            replay=replay,
        )

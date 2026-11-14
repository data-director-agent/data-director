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

`dd_sdk.model_provider.configured_model` builds this adapter from an agent's settings.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from dd_sdk.model import ModelRequest, ModelResponse, Usage

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


def _only_ours(api_key: str | None) -> Callable[[Any], None]:
    """A request hook that keeps the client's own headers and sets `api_key` as the bearer token,
    or none when there is no key."""

    def hook(request: Any) -> None:
        for name in list(request.headers):
            lowered = name.lower()
            if lowered not in _OWN_HEADERS and not lowered.startswith(_OWN_PREFIX):
                del request.headers[name]
        if api_key:
            request.headers["Authorization"] = f"Bearer {api_key}"

    return hook


def openai_client(base_url: str, api_key: str | None, *, http_client: Any = None) -> openai.OpenAI:
    """A Chat Completions client for `base_url` that sends `api_key`, or no key, and nothing it
    finds in the environment. `http_client` replaces the client's own HTTP client, for tests."""
    import openai as _openai

    if http_client is None:
        http_client = _openai.DefaultHttpxClient()
    http_client.event_hooks["request"] = [*http_client.event_hooks["request"], _only_ours(api_key)]
    return _openai.OpenAI(
        # The client insists on a key; with none, the hook sends no Authorization header.
        api_key=api_key or "unused",
        base_url=base_url,
        http_client=http_client,
    )


class OpenAIModel:
    """A model behind an OpenAI-compatible endpoint. Give a `client` (tests) or a `base_url`, and
    the `api_key` if the endpoint needs one.

    `provider` and `hosting` are what the agent's card declares (`dd_sdk.model.declared`).
    `max_tokens_field` is the request field that caps the reply: OpenAI's own API wants
    `max_completion_tokens`, and most other servers `max_tokens`."""

    def __init__(
        self,
        model_id: str,
        *,
        provider: str,
        hosting: Literal["hosted", "local"],
        base_url: str | None = None,
        api_key: str | None = None,
        max_tokens_field: str = "max_tokens",
        client: openai.OpenAI | None = None,
    ) -> None:
        if client is None:
            if base_url is None:
                raise ValueError("OpenAIModel needs a client or a base_url")
            client = openai_client(base_url, api_key)
        self._client = client
        self.model_id = model_id
        self.provider = provider
        self.hosting: Literal["hosted", "local"] = hosting
        self._max_tokens_field = max_tokens_field

    def send(self, request: ModelRequest) -> ModelResponse:
        messages: list[dict[str, Any]] = [{"role": "system", "content": request.system}]
        for sent in request.messages:
            if not isinstance(sent.get("content"), str):
                raise TypeError("OpenAIModel sends text messages only")
            messages.append(dict(sent))
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            self._max_tokens_field: request.max_tokens,
        }
        if request.schema is not None:
            from openai.lib import type_to_response_format_param

            # Structured output: the reply is constrained to the class as a strict JSON schema.
            # `dd_sdk.model.call` parses the text, so a reply that is not an instance is recorded
            # before it is refused.
            kwargs["response_format"] = type_to_response_format_param(request.schema)
        response = self._client.chat.completions.create(**kwargs)
        reply = response.choices[0].message if response.choices else None
        usage = getattr(response, "usage", None)
        return ModelResponse(
            text=(reply.content or "") if reply else "",
            refused=bool(reply and getattr(reply, "refusal", None)),
            model_id=getattr(response, "model", None) or None,
            usage=Usage(
                getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)
            ),
        )

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
(docs/specs/model-accounts.md).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dd_sdk.credentials import ModelEndpoint
from dd_sdk.model import ModelRequest, ModelResponse, Usage, current_grant
from dd_sdk.model_grant import HEADER_GRANT

if TYPE_CHECKING:
    import anthropic

# Who serves the model, as an agent's card names it (`dd_sdk.agent.ModelUse`).
PROVIDER = "anthropic"


def anthropic_client(endpoint: ModelEndpoint, *, http_client: Any = None) -> anthropic.Anthropic:
    """A Messages API client for `endpoint`. Through the broker, every request carries the current
    run's model grant. `http_client` replaces the client's own HTTP client, for tests."""
    import anthropic as _anthropic

    options: dict[str, Any] = {"api_key": endpoint.api_key, "base_url": endpoint.base_url}
    if http_client is not None:
        options["http_client"] = http_client
    if not endpoint.brokered:
        return _anthropic.Anthropic(**options)

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


class AnthropicModel:
    """Claude, by model id. Give a `client` (tests), an `endpoint`
    (`dd_sdk.credentials.model_endpoint`) or an `api_key`."""

    provider = PROVIDER

    def __init__(
        self,
        model_id: str,
        *,
        api_key: str | None = None,
        endpoint: ModelEndpoint | None = None,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        if client is None:
            if endpoint is None:
                if not api_key:
                    raise ValueError("AnthropicModel needs a client, an endpoint or an api_key")
                endpoint = ModelEndpoint(api_key)
            client = anthropic_client(endpoint)
        self._client = client
        self.model_id = model_id

    def send(self, request: ModelRequest) -> ModelResponse:
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": request.max_tokens,
            "system": request.system,
            "messages": [dict(m) for m in request.messages],
        }
        if request.schema is not None:
            import anthropic as _anthropic

            # Structured output: the reply is constrained to the schema, adapted to what the
            # API accepts (closed objects, supported keywords).
            kwargs["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "schema": _anthropic.transform_schema(request.schema),
                }
            }
        response = self._client.messages.create(**kwargs)
        usage = getattr(response, "usage", None)
        return ModelResponse(
            text="".join(block.text for block in response.content if block.type == "text"),
            refused=response.stop_reason == "refusal",
            model_id=getattr(response, "model", None),
            usage=Usage(
                getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None)
            ),
        )

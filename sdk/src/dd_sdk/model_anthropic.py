"""The `dd_sdk.model` adapter for Claude, through the Messages API.

This is the SDK's only importer of the `anthropic` package, which is the SDK's optional
`anthropic` extra (docs/specs/dependencies.md). The import is made when an `AnthropicModel` is
built without a client, or is asked for structured output, so the SDK imports without it.

The key is always passed explicitly (`dd_sdk.credentials.api_key`), so the `anthropic` package's
own credential chain is never used (docs/specs/policy-and-identity.md).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dd_sdk.model import ModelRequest, ModelResponse, Usage

if TYPE_CHECKING:
    import anthropic

# Who serves the model, as an agent's card names it (`dd_sdk.agent.ModelUse`).
PROVIDER = "anthropic"


class AnthropicModel:
    """Claude, by model id. Give a `client` (tests) or an `api_key`."""

    provider = PROVIDER

    def __init__(
        self,
        model_id: str,
        *,
        api_key: str | None = None,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ValueError("AnthropicModel needs a client or an api_key")
            import anthropic as _anthropic

            client = _anthropic.Anthropic(api_key=api_key)
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

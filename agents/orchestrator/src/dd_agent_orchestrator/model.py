"""The orchestrator's one way to the model, and its only importer of `anthropic` (ADR-0006).

`Model.turn` sends the conversation so far, with the tools the run built from the manifest, and
returns one `ModelTurn`: the text, the tool calls, why the model stopped, and the assistant
content to append unchanged before the next turn (thinking blocks included, which the API
requires back as they were sent). The orchestrator's loop knows nothing else about the API.

The request offers the model only the delegation tools it is given. It carries no MCP server,
server tool or Skills container (ADR-0012 decision 15, `tests/test_orchestrator_only_delegates.py`).

The key is passed in explicitly, so the SDK's own credential chain is never searched (ADR-0026).
Refusals fall back server-side (`fallbacks: "default"`), which routes a declined request to
another model by the refusal's category; a refusal that survives the fallback is a `ModelError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

import anthropic
from anthropic.types.beta import (
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolChoiceParam,
    BetaToolParam,
)

from dd_agent_orchestrator.prompt import SYSTEM_PROMPT

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_EFFORT = "high"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Room for a reply and the tool calls before it; a turn that reaches it is reported as cut short.
MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ModelError(Exception):
    """The model gave no usable turn: the API failed, or it declined the request."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ModelTurn:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str
    # The assistant message's content, as the API returned it, to be sent back unchanged.
    content: list[dict[str, Any]]
    # The model that answered, which differs from the one asked when a fallback served it.
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0


class Model(Protocol):
    model_id: str

    def turn(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, use_tools: bool
    ) -> ModelTurn: ...


class AnthropicModel:
    """Claude through the Messages API. Give a `client` (tests) or an `api_key`."""

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        *,
        model_id: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
        api_key: str | None = None,
    ) -> None:
        if client is None:
            if not api_key:
                raise ValueError("AnthropicModel needs a client or an api_key")
            client = anthropic.Anthropic(api_key=api_key)
        self._client = client
        self.model_id = model_id
        self.effort = effort

    def turn(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, use_tools: bool
    ) -> ModelTurn:
        # The prompt is fixed, so it caches across runs and turns.
        system: list[BetaTextBlockParam] = [
            {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
        ]
        tool_choice: BetaToolChoiceParam = {"type": "auto"} if use_tools else {"type": "none"}
        try:
            response = self._client.beta.messages.create(
                model=self.model_id,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=cast(list[BetaMessageParam], messages),
                tools=cast(list[BetaToolParam], tools),
                tool_choice=tool_choice,
                output_config={"effort": cast(Any, self.effort)},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.APIStatusError as exc:
            raise ModelError(f"the Messages API answered {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ModelError(f"the Messages API could not be reached: {exc}") from exc
        if response.stop_reason == "refusal":
            details = response.stop_details
            category = getattr(details, "category", None) if details else None
            raise ModelError(f"the model declined the request (category: {category or 'none'})")
        return ModelTurn(
            text="".join(b.text for b in response.content if b.type == "text"),
            tool_calls=[
                ToolCall(id=b.id, name=b.name, input=dict(b.input))
                for b in response.content
                if b.type == "tool_use"
            ],
            stop_reason=str(response.stop_reason),
            content=[
                b.model_dump(mode="json", by_alias=True, exclude_none=True)
                for b in response.content
            ],
            model_id=response.model,
            # Cached input is still input the model read.
            input_tokens=response.usage.input_tokens
            + (response.usage.cache_read_input_tokens or 0)
            + (response.usage.cache_creation_input_tokens or 0),
            output_tokens=response.usage.output_tokens,
        )

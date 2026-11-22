"""Gateway-side limits on one request's size, for the LiteLLM proxy.

A budget stops spending after the fact, and the request that crosses it is still allowed. This
hook bounds what a single request can cost before it is sent:

- a request that names no output limit gets `default_max_tokens`, so a caller that forgets
  `max_tokens` cannot ask the provider for the model's whole output window;
- a request that names an output limit above `max_output_tokens` is refused (HTTP 400);
- a request whose prompt is larger than `max_input_chars` is refused (HTTP 413). Characters
  stand in for tokens, at about four per token, because counting them would need each
  provider's tokenizer. LiteLLM's own `max_request_size_mb` is an Enterprise feature, so it
  cannot do this on the free tier.

The limits are `general_settings.dd_token_guard` in the gateway's config.yaml. It loads from the
directory that holds the config, and is named under `litellm_settings.callbacks`.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from litellm.integrations.custom_logger import CustomLogger

DEFAULTS: dict[str, int] = {
    "default_max_tokens": 4096,
    "max_output_tokens": 32000,
    "max_input_chars": 1_000_000,
}

# Call types that generate text, and the request field each uses for its output limit.
_OUTPUT_FIELD: dict[str, str] = {
    "completion": "max_tokens",
    "acompletion": "max_tokens",
    "text_completion": "max_tokens",
    "atext_completion": "max_tokens",
    "anthropic_messages": "max_tokens",
    "responses": "max_output_tokens",
    "aresponses": "max_output_tokens",
}
_LIMIT_FIELDS = ("max_tokens", "max_completion_tokens", "max_output_tokens")
_PROMPT_FIELDS = ("messages", "input", "system", "prompt", "tools")


def _prompt_chars(data: dict[str, Any]) -> int:
    prompt = {k: data[k] for k in _PROMPT_FIELDS if data.get(k) is not None}
    return len(json.dumps(prompt, default=str))


class TokenGuard(CustomLogger):
    """Applies the limits above before a request reaches a provider."""

    def __init__(self, settings: dict[str, int] | None = None) -> None:
        super().__init__()
        self._settings = settings

    def limits(self) -> dict[str, int]:
        settings = self._settings
        if settings is None:
            from litellm.proxy.proxy_server import general_settings

            settings = general_settings.get("dd_token_guard") or {}
        return {**DEFAULTS, **settings}

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: dict[str, Any],
        call_type: str,
    ) -> dict[str, Any]:
        field = _OUTPUT_FIELD.get(call_type)
        if field is None:
            return data
        limits = self.limits()

        chars = _prompt_chars(data)
        if chars > limits["max_input_chars"]:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Prompt is too large: {chars} characters, and this gateway allows "
                    f"{limits['max_input_chars']}. Send less, or ask the operator to raise "
                    "dd_token_guard.max_input_chars."
                ),
            )

        named = {f: data[f] for f in _LIMIT_FIELDS if data.get(f) is not None}
        if not named:
            data[field] = limits["default_max_tokens"]
            return data
        for name, value in named.items():
            if isinstance(value, int) and value > limits["max_output_tokens"]:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{name}={value} is over this gateway's limit of "
                        f"{limits['max_output_tokens']} output tokens. Ask for less, or ask the "
                        "operator to raise dd_token_guard.max_output_tokens."
                    ),
                )
        return data


proxy_handler_instance = TokenGuard()

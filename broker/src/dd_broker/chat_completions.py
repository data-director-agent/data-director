"""Forwarding a call in the OpenAI Chat Completions format (docs/specs/model-accounts.md).

An agent whose provider is `openai`, `gemini` or `openai-compatible` points its OpenAI client at
the broker's `/{provider}` base URL, so its calls arrive at `/{provider}/chat/completions`. The
path names the provider the agent's card declares, and the broker serves that provider or refuses
(invariant 12). The broker forwards the request body unchanged to `{base}/chat/completions` with
the key of whichever account pays as `Authorization: Bearer`, and returns the provider's answer.
Provider HTTP is plumbing, so this is a thin `httpx` call; the governance is in `dd_broker.app`.

No header is passed on from the agent's request: its credential, its grant and every other header
stay with the broker.

`check_key` is the one inexpensive call the broker makes before it stores a person's key
(docs/specs/model-accounts.md, Enrolment): listing the models costs no tokens.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from dd_broker.guard import Target

COMPLETIONS_PATH = "/chat/completions"
MODELS_PATH = "/models"
# A gateway serves the Chat Completions format below `/v1`, as LiteLLM does.
GATEWAY_PATH = "/v1"
TIMEOUT_S = httpx.Timeout(600.0, connect=10.0)
CHECK_TIMEOUT_S = httpx.Timeout(20.0, connect=10.0)


@dataclass(frozen=True)
class ChatProvider:
    """A provider the broker serves in this format: its name (as `DD_MODEL_PROVIDER` names it),
    its fixed endpoint (None: the account's own base URL), the variable the deployment's key is
    read from, and how a label names it."""

    name: str
    base_url: str | None
    deployment_key: str
    title: str | None = None


COMPATIBLE = "openai-compatible"

PROVIDERS = {
    p.name: p
    for p in (
        ChatProvider("openai", "https://api.openai.com/v1", "OPENAI_API_KEY", "OpenAI"),
        ChatProvider(
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            "GEMINI_API_KEY",
            "Gemini",
        ),
        # No endpoint of its own: a person's account names one, and the deployment's calls go
        # only through the gateway.
        ChatProvider(COMPATIBLE, None, "DD_MODEL_API_KEY"),
    )
}


def _headers(key: str, target: Target) -> dict[str, str]:
    return {"authorization": f"Bearer {key}", **target.headers}


async def send(
    client: httpx.AsyncClient,
    target: Target,
    key: str,
    body: Mapping[str, Any],
    headers: Mapping[str, str],
) -> httpx.Response:
    del headers  # nothing is passed on from the agent's request
    return await client.post(
        target.url + COMPLETIONS_PATH,
        json=body,
        headers={**_headers(key, target), "content-type": "application/json"},
        timeout=TIMEOUT_S,
        extensions=target.extensions,
    )


def usage(answer: Mapping[str, Any]) -> tuple[int, int]:
    """Input and output tokens from a Chat Completions answer. `prompt_tokens` already counts
    cached input."""
    counts = answer.get("usage")
    if not isinstance(counts, Mapping):
        return 0, 0

    def number(name: str) -> int:
        value = counts.get(name)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    return number("prompt_tokens"), number("completion_tokens")


async def check_key(client: httpx.AsyncClient, target: Target, key: str) -> int:
    """Ask the endpoint to list its models with `key`, and return only the status. The answer's
    body is never read, since an endpoint's error text may quote the key. Raises
    `httpx.HTTPError` if the endpoint cannot be reached."""
    answer = await client.get(
        target.url + MODELS_PATH,
        headers=_headers(key, target),
        timeout=CHECK_TIMEOUT_S,
        extensions=target.extensions,
    )
    return answer.status_code


def label(provider: ChatProvider, key: str, base_url: str | None) -> str:
    """What the page shows of an account: the provider, or for an OpenAI-compatible endpoint its
    host, and the key's last four characters."""
    name = provider.title or (urlsplit(base_url or "").hostname or provider.name)
    return f"{name} ····{key[-4:]}"

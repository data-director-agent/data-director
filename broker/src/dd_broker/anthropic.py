"""Forwarding a call in the Anthropic Messages API format (docs/specs/model-accounts.md).

An agent's Anthropic client points at the broker's `/anthropic` base URL. The broker forwards the
request body unchanged to `{base}/v1/messages` with the key of whichever account pays, and
returns the provider's answer. Provider HTTP is plumbing, so this is a thin `httpx` call; the
governance is in `dd_broker.app`.

Only `anthropic-version` and `anthropic-beta` are passed on from the agent's request. Its
credential, its grant and every other header stay with the broker.

`check_key` is the one inexpensive call the broker makes before it stores a person's key
(docs/specs/model-accounts.md, Enrolment): listing one model costs no tokens.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from dd_broker.guard import Target

PROVIDER = "anthropic"
BASE_URL = "https://api.anthropic.com"
MESSAGES_PATH = "/v1/messages"
MODELS_PATH = "/v1/models"
DEFAULT_VERSION = "2023-06-01"
PASSED_HEADERS = ("anthropic-version", "anthropic-beta")
TIMEOUT_S = httpx.Timeout(600.0, connect=10.0)
CHECK_TIMEOUT_S = httpx.Timeout(20.0, connect=10.0)


async def send(
    client: httpx.AsyncClient,
    target: Target,
    key: str,
    body: Mapping[str, Any],
    headers: Mapping[str, str],
) -> httpx.Response:
    outgoing = {name: headers[name] for name in PASSED_HEADERS if name in headers}
    outgoing.setdefault("anthropic-version", DEFAULT_VERSION)
    outgoing["x-api-key"] = key
    outgoing["content-type"] = "application/json"
    outgoing.update(target.headers)
    return await client.post(
        target.url + MESSAGES_PATH,
        json=body,
        headers=outgoing,
        timeout=TIMEOUT_S,
        extensions=target.extensions,
    )


def usage(answer: Mapping[str, Any]) -> tuple[int, int]:
    """Input and output tokens from a Messages API answer, counting cache reads and writes as
    input."""
    counts = answer.get("usage")
    if not isinstance(counts, Mapping):
        return 0, 0

    def number(name: str) -> int:
        value = counts.get(name)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    input_tokens = (
        number("input_tokens")
        + number("cache_creation_input_tokens")
        + number("cache_read_input_tokens")
    )
    return input_tokens, number("output_tokens")


async def check_key(client: httpx.AsyncClient, target: Target, key: str) -> int:
    """Ask the provider to list one model with `key`, and return only the status. The answer's
    body is never read, since a provider's error text may quote the key. Raises
    `httpx.HTTPError` if the provider cannot be reached."""
    answer = await client.get(
        target.url + MODELS_PATH,
        params={"limit": 1},
        headers={"x-api-key": key, "anthropic-version": DEFAULT_VERSION, **target.headers},
        timeout=CHECK_TIMEOUT_S,
        extensions=target.extensions,
    )
    return answer.status_code


def label(key: str) -> str:
    """What the page shows of an Anthropic account: the provider and the key's last four
    characters. Anthropic's API names no account, so there is no account name to add."""
    return f"Anthropic ····{key[-4:]}"

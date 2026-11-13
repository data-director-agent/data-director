"""A conversation's title, written by a small model on its first turn (docs/specs/contract.md,
`Reply.conversation_title`).

The app lists earlier conversations by title, and it calls no model
(docs/specs/policy-and-identity.md), so the agent that holds the key writes one. `titled` makes
one call, sent only the researcher's first message, which the prompt (`title_prompt.md`) treats
as data, not instructions. The call is recorded like the orchestrator's own: a `chat` span with
its tokens, and an entry in the run's `ModelCallLog`, so its prompt is disclosed with the run.

A title is a convenience. Any failure (the API, a refusal, an empty or unusable answer) gives no
title, and the turn succeeds without one; the harness then names the conversation by the start
of its first message (docs/specs/orchestration.md).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import anthropic

from dd_sdk.agent import RunContext
from dd_sdk.contract.models import CONVERSATION_TITLE_MAX, now
from dd_sdk.credentials import ModelEndpoint
from dd_sdk.model_anthropic import anthropic_client
from dd_sdk.prompts import ModelCallLog
from dd_sdk.tracing import ATTR_MODEL_ID, chat_span, record_tokens

log = logging.getLogger(__name__)

DEFAULT_TITLE_MODEL = "claude-haiku-5-5"
# A title is two to six words; this leaves room without paying for a paragraph.
TITLE_MAX_TOKENS = 32
TITLE_PROMPT = Path(__file__).with_name("title_prompt.md").read_text(encoding="utf-8").strip()
# What the model may wrap a title in, which is not part of it.
QUOTES = "\"'`\u201c\u201d\u2018\u2019\u00ab\u00bb"
ELLIPSIS = "…"


class TitleError(Exception):
    """The model gave no usable title."""


@dataclass(frozen=True)
class TitleTurn:
    """What the title model answered: its text, the model the response named, and the tokens."""

    text: str
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0


class Titler(Protocol):
    model_id: str

    def turn(self, prompt: dict[str, Any]) -> TitleTurn:
        """Send `prompt` (`title_prompt`) and return the answer, or raise `TitleError`."""
        ...


def title_prompt(message_text: str) -> dict[str, Any]:
    """What is sent: the system prompt and the first message, marked off as data."""
    return {
        "system": TITLE_PROMPT,
        "messages": [{"role": "user", "content": f"<message>\n{message_text}\n</message>"}],
    }


def clean(text: str) -> str | None:
    """The first line of `text`, without quotes, a trailing full stop or runs of spaces, cut to
    `CONVERSATION_TITLE_MAX` characters at a word where it can be. None if nothing is left."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    title = " ".join(lines[0].split()).strip(QUOTES + " ")
    title = re.sub(r"^(title|conversation title)\s*:\s*", "", title, flags=re.IGNORECASE)
    title = title.strip(QUOTES + " ").rstrip(".").strip(QUOTES + " ")
    if not title:
        return None
    if len(title) > CONVERSATION_TITLE_MAX:
        cut = title[: CONVERSATION_TITLE_MAX - len(ELLIPSIS)]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        title = cut.rstrip(" ,;:-") + ELLIPSIS
    return title


@dataclass(frozen=True)
class Title:
    text: str
    input_tokens: int
    output_tokens: int


def titled(titler: Titler, message_text: str, ctx: RunContext, calls: ModelCallLog) -> Title | None:
    """One call for a title, recorded in `calls` and the trace. None, never an error, if there
    is no title to give."""
    if not message_text.strip():
        return None
    prompt = title_prompt(message_text)
    called_at = now()
    try:
        with chat_span(ctx.tracer, titler.model_id) as span:
            turn = titler.turn(prompt)
            if turn.model_id != titler.model_id:
                span.set_attribute(ATTR_MODEL_ID, turn.model_id)
            record_tokens(span, turn.input_tokens, turn.output_tokens)
    except Exception as exc:  # noqa: BLE001 — a title is never worth failing the turn for
        log.warning("no conversation title: %s", exc)
        return None
    calls.record(
        prompt,
        turn.model_id,
        called_at=called_at,
        input_tokens=turn.input_tokens,
        output_tokens=turn.output_tokens,
    )
    text = clean(turn.text)
    if text is None:
        log.warning("no conversation title: the model gave none")
        return None
    return Title(text, turn.input_tokens, turn.output_tokens)


class AnthropicTitler:
    """Claude through the Messages API. Give a `client` (tests) or an `endpoint`
    (`dd_sdk.credentials.model_endpoint`), whose credential is passed explicitly so the SDK's own
    credential chain is never searched (docs/specs/policy-and-identity.md)."""

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        *,
        model_id: str = DEFAULT_TITLE_MODEL,
        endpoint: ModelEndpoint | None = None,
    ) -> None:
        if client is None:
            if endpoint is None:
                raise ValueError("AnthropicTitler needs a client or an endpoint")
            client = anthropic_client(endpoint)
        self._client = client
        self.model_id = model_id

    def turn(self, prompt: dict[str, Any]) -> TitleTurn:
        try:
            response = self._client.messages.create(
                model=self.model_id,
                max_tokens=TITLE_MAX_TOKENS,
                system=prompt["system"],
                messages=prompt["messages"],
            )
        except anthropic.APIError as exc:
            raise TitleError(f"the Messages API failed: {exc}") from exc
        if response.stop_reason == "refusal":
            raise TitleError("the model declined to give a title")
        return TitleTurn(
            text="".join(b.text for b in response.content if b.type == "text"),
            model_id=getattr(response, "model", None) or self.model_id,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

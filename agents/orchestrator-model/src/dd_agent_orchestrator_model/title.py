"""A conversation's title, written by a small model on its first turn (docs/specs/contract.md,
`Reply.conversation_title`).

The app lists earlier conversations by title, and it calls no model
(docs/specs/policy-and-identity.md), so the agent that holds the key writes one. `titled` makes
one call through the SDK's model seam (`dd_sdk.model.call`), sent only the researcher's first
message, which the prompt (`title_prompt.md`) treats as data, not instructions. The call is
recorded like the orchestrator's own: a `chat` span with its tokens, and an entry in the run's
`ModelCallLog`, so its prompt is disclosed with the run.

A title is a convenience. Any failure (the API, a refusal, an empty or unusable answer) gives no
title, and the turn succeeds without one; the harness then names the conversation by the start
of its first message (docs/specs/orchestration.md).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dd_sdk.agent import RunContext
from dd_sdk.contract.models import CONVERSATION_TITLE_MAX
from dd_sdk.model import CallOptions, Model, call
from dd_sdk.prompts import ModelCallLog

log = logging.getLogger(__name__)

DEFAULT_TITLE_MODEL = "claude-haiku-5-5"
# A title is two to six words; this leaves room without paying for a paragraph.
TITLE_MAX_TOKENS = 32
TITLE_PROMPT = Path(__file__).with_name("title_prompt.md").read_text(encoding="utf-8").strip()
# What the model may wrap a title in, which is not part of it.
QUOTES = "\"'`\u201c\u201d\u2018\u2019\u00ab\u00bb"
ELLIPSIS = "…"


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


def titled(model: Model, message_text: str, ctx: RunContext, calls: ModelCallLog) -> Title | None:
    """One call for a title, recorded in `calls` and the trace. None, never an error, if there
    is no title to give."""
    if not message_text.strip():
        return None
    prompt = title_prompt(message_text)
    try:
        reply = call(
            model,
            ctx,
            system=prompt["system"],
            messages=prompt["messages"],
            options=CallOptions(max_tokens=TITLE_MAX_TOKENS, calls=calls),
        )
    except Exception as exc:  # noqa: BLE001 — a title is never worth failing the turn for
        log.warning("no conversation title: %s", exc)
        return None
    text = None if reply.refused else clean(reply.text)
    if text is None:
        log.warning("no conversation title: the model gave none")
        return None
    return Title(text, reply.usage.input_tokens or 0, reply.usage.output_tokens or 0)

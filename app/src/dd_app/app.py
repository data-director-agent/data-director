"""The browser chat: a Gradio `ChatInterface` around the agent in `agent.py`.

Serves on http://127.0.0.1:7860 by default and opens a browser. Gradio's own
`GRADIO_SERVER_NAME` and `GRADIO_SERVER_PORT` change the address.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import gradio as gr
from pydantic_ai.exceptions import UserError

from dd_app.agent import build_agent, respond

TITLE = "Data Director (alpha)"
DESCRIPTION = (
    "An alpha assistant for documenting, publishing and sharing research data. It is not "
    "governed by the workbench: nothing it says is checked or recorded, and its advice needs "
    "human review. Standards are looked up in a small offline FAIRsharing snapshot "
    "(CC BY-SA 4.0, https://fairsharing.org)."
)
EXAMPLES = [
    "Which metadata standards suit a single-cell RNA-seq dataset?",
    "I have gridded climate model output. What open formats and vocabularies should I use?",
    "What should a README for a survey dataset contain?",
]


def build_app() -> gr.ChatInterface:
    try:
        agent = build_agent()
    except UserError as exc:
        sys.exit(f"Cannot start the model: {exc}\nSet DD_CHAT_MODEL or the provider's API key.")

    async def chat(message: str, history: list[dict[str, Any]]) -> list[gr.ChatMessage]:
        turn = await respond(agent, message, history)
        notes = [
            gr.ChatMessage(
                content=f"`{call.args_as_json_str()}`",
                metadata={"title": f"Tool: {call.tool_name}", "status": "done"},
            )
            for call in turn.tool_calls
        ]
        return [*notes, gr.ChatMessage(content=turn.answer)]

    return gr.ChatInterface(
        chat,
        title=TITLE,
        description=DESCRIPTION,
        examples=EXAMPLES,
        cache_examples=False,
        analytics_enabled=False,
    )


def main() -> int:
    """The `data-director` console script."""
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # pydantic-ai's advertising banner
    build_app().launch(inbrowser=True)
    return 0

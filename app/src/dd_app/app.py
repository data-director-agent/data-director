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

from dd_app.agent import Governance, build_agent, respond
from dd_app.config import settings_from_env
from dd_harness.identity import IdentityError
from dd_harness.policy import PolicyError
from dd_harness.registry import RegistryError
from dd_harness.settings import SettingsError
from dd_harness.sources import SourceConfigError

TITLE = "Data Director (alpha)"
DESCRIPTION = (
    "An alpha assistant for documenting, publishing and sharing research data. Standards "
    "are recommended from a small offline FAIRsharing snapshot (CC BY-SA 4.0, "
    "https://fairsharing.org); each recommendation run is checked and recorded. The "
    "assistant's own wording is not checked, and its advice needs human review."
)
EXAMPLES = [
    "Which metadata standards suit a single-cell RNA-seq dataset?",
    "I have gridded climate model output. What open formats and vocabularies should I use?",
    "What should a README for a survey dataset contain?",
]


def build_app() -> gr.ChatInterface:
    try:
        governance = Governance.create(settings_from_env())
    # No principal (ADR-0018), or a profile, agent list or source list that is unset, missing
    # or malformed (ADR-0022): nothing may run.
    except (IdentityError, SettingsError, PolicyError, RegistryError, SourceConfigError) as exc:
        sys.exit(f"data-director: {exc}")
    try:
        agent = build_agent(governance)
    except UserError as exc:
        sys.exit(f"Cannot start the model: {exc}\nSet DD_CHAT_MODEL or the provider's API key.")

    async def chat(message: str, history: list[dict[str, Any]]) -> list[gr.ChatMessage]:
        turn = await respond(agent, message, history)
        notes = [
            gr.ChatMessage(
                content=f"`{call.args_as_json_str()}`"
                + (
                    f"\n\nRecorded as run `{run}`."
                    if (run := turn.runs.get(call.tool_call_id))
                    else ""
                ),
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

"""The note's suggested step is one an agent serves where its phase has one, and the prompt says
a step has an agent only when a tool names it (#1377; docs/specs/orchestration.md, invariants 14
and 19)."""

from __future__ import annotations

import pytest

from dd_agent_orchestrator_model.notes import progress_note
from dd_agent_orchestrator_model.prompt import SYSTEM_PROMPT
from dd_sdk.contract.models import Message

pytestmark = pytest.mark.requirement("DD-CONVERSATION")

STANDARDS = {"agent_id": "advisor.standards", "serves": ["setup.vocabularies"]}


def test_the_note_suggests_the_phase_one_step_an_agent_serves() -> None:
    message = Message(message_text="Hello", project_entry=1, project_entry_by_researcher=True)
    served = progress_note(message, [STANDARDS])
    unserved = progress_note(message)
    assert served is not None and "Suggested next: [setup.vocabularies]" in served
    assert unserved is not None and "Suggested next: [setup.documentation]" in unserved


def test_the_prompt_ties_an_agent_to_the_steps_a_tool_names() -> None:
    assert "Serves step(s)" in SYSTEM_PROMPT

"""The orchestrator passes on an agent's advice instead of turning it into a bare menu: it keeps
the agent's order and reasons, groups recommendations by kind, and asks the researcher to choose
only when their answer is recorded or used (docs/specs/orchestration.md, Rationale)."""

from __future__ import annotations

from typing import Any

import pytest

from dd_agent_orchestrator_model.own_tools import QUESTIONS_TOOL_DEFINITION
from dd_agent_orchestrator_model.prompt import SYSTEM_PROMPT

pytestmark = pytest.mark.requirement("DD-CONVERSATION")


def _option_properties() -> dict[str, Any]:
    question = QUESTIONS_TOOL_DEFINITION.input_schema["properties"]["questions"]["items"]
    options: dict[str, Any] = question["properties"]["question_options"]["items"]["properties"]
    return options


def test_an_options_help_carries_the_agents_reason() -> None:
    assert "reason" in _option_properties()["option_help"]["description"]


def test_the_prompt_keeps_an_agents_order_and_does_not_forbid_ranking() -> None:
    assert "keep the agent's order" in SYSTEM_PROMPT
    assert "pre-select or rank" not in SYSTEM_PROMPT


def test_the_prompt_asks_for_a_choice_only_when_it_is_recorded_or_used() -> None:
    assert "only when their answer is recorded" in SYSTEM_PROMPT
    assert "group them by kind" in SYSTEM_PROMPT

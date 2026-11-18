"""A researcher who asks in chat to leave files out is pointed to **Edit inventory**, because the
conversation cannot change the inventory (#1171)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dd_agent_example_hello.agent import HelloWorld
from dd_agent_orchestrator_model import factory
from dd_agent_orchestrator_model.prompt import SYSTEM_PROMPT
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import Message, OutcomeStatus, Reply

pytestmark = pytest.mark.requirement("DD-CONVERSATION")


def test_the_system_prompt_sends_exclusions_to_edit_inventory() -> None:
    assert "Edit inventory" in SYSTEM_PROMPT
    assert "cannot change which files are in the dataset" in SYSTEM_PROMPT
    assert "do not say the drafts will follow on their own" in SYSTEM_PROMPT.lower()


@pytest.fixture(scope="module")
def vcr_config(vcr_config: dict[str, Any]) -> dict[str, Any]:
    def model_calls_only(request: Any) -> Any:
        return None if request.host.endswith(".test") else request

    return {
        **vcr_config,
        "before_record_request": model_calls_only,
        "match_on": ["method", "scheme", "host", "port", "path"],
    }


@pytest.mark.vcr
def test_an_exclusion_request_points_to_edit_inventory(runs_dir: Path) -> None:
    built = factory.build({"ANTHROPIC_API_KEY": "sk-ant-test"})
    conductor = make_conductor(runs_dir, built, HelloWorld())
    env = conductor.invoke(
        request(
            "orchestrator.model",
            Message(message_text="Please leave out batch B1: S1, S2 and images 1 to 3."),
        ),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert "Edit inventory" in env.payload_as(Reply).reply_text

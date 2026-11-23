"""The orchestrator offers an inventory before asking for what one gives (#1540): without one, it
points to the app's inventory maker and the command; with one, the note names every slot the
harness fills from it, so the model leaves them out of an agent's input, and it calls the
Repository Librarian without first asking the researcher to confirm the kinds of data (#1560)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dd_agent_orchestrator_model.notes import inventory_note
from dd_agent_orchestrator_model.prompt import SYSTEM_PROMPT
from dd_sdk.contract.facts import InventorySummary
from dd_sdk.contract.models import Message

pytestmark = pytest.mark.requirement("DD-CONVERSATION")


def test_the_system_prompt_offers_both_ways_to_make_an_inventory() -> None:
    assert "Make an inventory" in SYSTEM_PROMPT
    assert "uvx data-director-inventory" in SYSTEM_PROMPT


def test_the_inventory_note_names_the_slots_the_harness_fills() -> None:
    held = InventorySummary(
        inventory_digest="a" * 64,
        inventory_file_count=3,
        inventory_tool="dd-inventory",
        inventory_tool_version="0.1.0",
        inventory_made_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    note = inventory_note(Message(message_text="now", project_inventory=held))
    assert note is not None
    assert "`inventory`" in note and "`project_file_inventory`" in note


def test_with_an_inventory_the_repository_librarian_is_called_without_asking_first() -> None:
    """#1560: confirming the kinds of data before the search left a turn that neither asked nor
    delegated. The Repository Librarian takes the kinds from the inventory; they are confirmed
    after it reports."""
    assert "Call the Repository Librarian without asking first" in SYSTEM_PROMPT
    assert "leave `data_kinds` out" in SYSTEM_PROMPT

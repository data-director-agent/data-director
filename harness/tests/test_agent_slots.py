"""Which core slots an agent's own input class asks the conductor to fill, read from the agent's
card (docs/specs/projects.md, invariant 6; `dd_harness.agent_slots`)."""

from __future__ import annotations

from dd_harness.agent_slots import AGENT_INPUT_SLOTS, CORE_CLASSES, agent_slots
from dd_harness.testing import FactStub


def test_a_class_mixing_in_the_project_slots_asks_for_them_by_name() -> None:
    slots = agent_slots(FactStub().spec, "ProbeReading")
    assert "project_plan_approved" in slots
    assert slots <= set(AGENT_INPUT_SLOTS)


def test_a_core_class_an_unknown_card_or_a_class_not_accepted_asks_for_none() -> None:
    spec = FactStub().spec
    for schema_class in CORE_CLASSES:
        assert agent_slots(spec, schema_class) == frozenset()
    assert agent_slots(None, "ProbeReading") == frozenset()
    assert agent_slots(spec, "NotAClassItAccepts") == frozenset()

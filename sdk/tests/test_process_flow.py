"""The Blueprint's process flow, and the plan it gives each entry point from a manifest."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dd_sdk.process_flow import (
    ENTRIES,
    PHASES,
    REQUIREMENTS,
    STEPS,
    describe_flow,
    entry,
    plan,
    requirements_of,
)

REGISTER = Path(__file__).resolve().parents[2] / "docs" / "requirements.yaml"


def test_three_entry_points_join_at_phases_one_two_and_three() -> None:
    assert [(e.number, e.starts_at) for e in ENTRIES] == [(1, 1), (2, 2), (3, 3)]
    assert [p.number for p in PHASES] == [1, 2, 3, 4, 5, 6]
    with pytest.raises(KeyError):
        entry(4)


def test_every_requirement_a_step_names_is_a_blueprint_requirement_in_the_register() -> None:
    register = yaml.safe_load(REGISTER.read_text(encoding="utf-8"))["requirements"]
    blueprint = {r["id"] for r in register if r["source"] == "blueprint"}
    named = {r for p in PHASES for s in p.steps for r in s.requirements}
    assert blueprint >= REQUIREMENTS
    assert named <= REQUIREMENTS


@pytest.mark.requirement("DD-ENTRY-POINTS")
def test_a_plan_runs_from_the_entry_to_the_last_phase_and_names_who_serves_each_step() -> None:
    manifest: list[dict[str, Any]] = [
        {"agent_id": "advisor.quality", "serves": ["deposit.validate"]},
        {"agent_id": "advisor.standards", "serves": ["setup.vocabularies", "preparation.formats"]},
        {"agent_id": "example.hello"},
    ]
    first = plan(entry(1), manifest)
    assert first[0].phase.number == 1 and first[-1].phase.number == 6
    by_text = {p.step.text: p.agent_ids for p in first}
    assert by_text["Select controlled vocabularies and ontologies"] == ("advisor.standards",)
    assert by_text["Recommend open formats"] == ("advisor.standards",)
    assert by_text["Validate metadata quality"] == ("advisor.quality",)
    assert by_text["Draft the data documentation"] == ()

    third = plan(entry(3), manifest)
    assert {p.phase.number for p in third} == {3, 4, 5, 6}


def test_every_step_has_a_unique_id_under_its_phase_and_none_is_a_requirement() -> None:
    ids = [s.id for p in PHASES for s in p.steps]
    assert len(ids) == len(set(ids)) == len(STEPS)
    assert not STEPS & REQUIREMENTS
    prefixes = {p.number: {s.id.split(".")[0] for s in p.steps} for p in PHASES}
    assert all(len(prefix) == 1 for prefix in prefixes.values())


def test_an_agent_is_planned_at_the_steps_it_names_and_no_other() -> None:
    manifest: list[dict[str, Any]] = [
        {"agent_id": "advisor.policy", "serves": ["governance.policies", "repository.mandated"]},
        {"agent_id": "metadata.advisor", "serves": ["setup.vocabularies"]},
    ]
    by_id = {p.step.id: p.agent_ids for p in plan(entry(1), manifest)}
    assert by_id["governance.policies"] == ("advisor.policy",)
    assert by_id["repository.mandated"] == ("advisor.policy",)
    assert by_id["governance.embargo"] == ()
    # Serving one R3 step does not place an agent at every step that names R3.
    assert by_id["setup.vocabularies"] == ("metadata.advisor",)
    assert by_id["preparation.formats"] == ()


def test_the_requirements_an_agent_bears_on_follow_from_its_steps() -> None:
    assert requirements_of(["deposit.validate"]) == ("R4",)
    assert requirements_of(["preparation.metadata", "setup.vocabularies", "post.retrofit"]) == (
        "R2",
        "R3",
        "R6",
        "R9",
    )
    assert requirements_of(["governance.policies"]) == ()


def test_the_prompt_text_names_every_entry_phase_and_requirement() -> None:
    text = describe_flow()
    for e in ENTRIES:
        assert f"Entry {e.number}:" in text
    for p in PHASES:
        assert f"Phase {p.number}: {p.title}" in text
    named = {r for p in PHASES for s in p.steps for r in s.requirements}
    assert all(r in text for r in named)
    assert all(f"[{s}]" in text for s in STEPS)

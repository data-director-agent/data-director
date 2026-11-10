"""The Blueprint's process flow, and the plan it gives each entry point from a manifest."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dd_sdk.process_flow import (
    ENTRIES,
    OUT_OF_SCOPE,
    PHASES,
    REQUIREMENTS,
    STEPS,
    describe_flow,
    entry,
    plan,
    progress,
    requirements_of,
    suggested_next,
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


def test_the_data_management_plan_steps_are_in_the_flow_and_out_of_scope_for_now() -> None:
    assert {"setup.dmp-create", "setup.dmp-review", "post.dmp-update"} == OUT_OF_SCOPE
    assert OUT_OF_SCOPE <= STEPS
    # Verifying a deposit against an existing plan (R8) stays in scope.
    assert "governance.dmp" not in OUT_OF_SCOPE
    # An out-of-scope step is still planned, so an orchestrator and the phase tracker show it,
    # with no agent.
    planned = {p.step.id: p for p in plan(entry(1), [])}
    assert all(planned[i].agent_ids == () for i in OUT_OF_SCOPE)
    assert [s.id for s in PHASES[0].steps][-2:] == ["setup.dmp-create", "setup.dmp-review"]
    text = describe_flow()
    line = next(x for x in text.splitlines() if "[setup.dmp-create]" in x)
    assert "optional" in line and "out of scope for now" in line


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


def test_every_phase_and_step_has_wording_for_researchers_free_of_requirement_ids() -> None:
    for phase in PHASES:
        assert phase.name and phase.summary
        for step in phase.steps:
            assert step.label, step.id
            assert not any(r in step.label for r in REQUIREMENTS), step.id


def test_progress_from_an_entry_keeps_earlier_work_and_marks_each_step() -> None:
    manifest: list[dict[str, Any]] = [
        {"agent_id": "advisor.files", "serves": ["preparation.files"]}
    ]
    states = {"setup.vocabularies": "done", "preparation.files": "started"}
    steps = progress(entry(3), states, manifest)
    # Phase 1 work done before the researcher's entry point still shows; Phase 2 does not.
    assert {s.phase.number for s in steps} == {1, 3, 4, 5, 6}
    by_id = {s.step.id: s for s in steps}
    assert by_id["setup.vocabularies"].state == "done"
    assert by_id["preparation.files"].state == "started"
    assert by_id["preparation.files"].agent_ids == ("advisor.files",)
    assert by_id["deposit.upload"].state == "open"
    # With no entry point, every phase.
    assert {s.phase.number for s in progress(None, {}, manifest)} == {1, 2, 3, 4, 5, 6}


def test_the_suggestion_is_the_first_open_step_from_the_entry_and_never_a_gate() -> None:
    start = entry(2)
    first = suggested_next(progress(start, {}, []), start)
    assert first is not None and first.step.id == "governance.policies"
    # Done and skipped steps are passed, whatever order they were done in; a step with no agent
    # is still suggested.
    states = {"governance.policies": "done", "governance.sensitive-data-identify": "skipped"}
    found = suggested_next(progress(start, states, []), start)
    assert found is not None and found.step.id == "governance.sensitive-data-handle"
    assert found.agent_ids == ()
    # A step begun is suggested before an earlier one not begun.
    states = {"preparation.metadata": "started"}
    begun = suggested_next(progress(start, states, []), start)
    assert begun is not None and begun.step.id == "preparation.metadata"


def test_the_suggestion_passes_optional_and_out_of_scope_steps_and_ends_when_all_are_done() -> None:
    start = entry(1)
    states = {"setup.documentation": "done", "setup.vocabularies": "done"}
    found = suggested_next(progress(start, states, []), start)
    # setup.dmp-create is optional and out of scope, setup.dmp-review out of scope.
    assert found is not None and found.step.id == "governance.policies"
    every = {s.id: "done" for p in PHASES for s in p.steps}
    assert suggested_next(progress(start, every, []), start) is None
    # Optional steps never hold the suggestion back.
    required = {
        s.id: "done" for p in PHASES for s in p.steps if not s.optional and not s.out_of_scope
    }
    assert suggested_next(progress(start, required, []), start) is None


def test_with_no_entry_point_only_a_started_step_is_suggested() -> None:
    # Where the researcher is is not known, so no Phase 1 step is put to them.
    assert suggested_next(progress(None, {}, []), None) is None
    states = {"setup.documentation": "done"}
    assert suggested_next(progress(None, states, []), None) is None
    states = {"preparation.metadata": "started"}
    begun = suggested_next(progress(None, states, []), None)
    assert begun is not None and begun.step.id == "preparation.metadata"

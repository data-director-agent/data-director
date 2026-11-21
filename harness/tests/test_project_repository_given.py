"""The repository a researcher chose, given to agents in a project (docs/specs/projects.md,
invariants 6 and 8; #1168): a `Message`'s `project_repository`, and an agent's own class that
mixes in `GivenProjectRepository`, name the repository chosen last. Only the conductor fills it,
and it is `decisions`, so a profile that keeps decisions from a hosted orchestrator leaves it out
rather than refusing the turn."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from requirement_sets import ORDA, override, pinned, standard, write

from dd_harness.conductor import Conductor
from dd_harness.projects import ProjectStore
from dd_harness.requirements import load_requirements
from dd_harness.testing import (
    TEST_PRINCIPAL,
    AbstainingStub,
    FactStub,
    ProbeReading,
    make_conductor,
    message,
    request,
)
from dd_sdk.agent import ModelUse
from dd_sdk.contract.models import (
    ChosenRepository,
    InvocationRequest,
    OutcomeStatus,
    new_invocation_id,
)

pytestmark = pytest.mark.requirement("C13.3")

FORGED = ChosenRepository(chosen_repository_name="Forged", chosen_re3data_id="r3d000000000")


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project(projects: ProjectStore) -> str:
    return projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Perovskite")


def choose(projects: ProjectStore, project: str, root: Path) -> dict[str, Any]:
    """Choose ORDA for `project`; returns what a `ChosenRepository` should say."""
    repositories = write(
        root / "repositories", ("standards", standard()), ("overrides", override())
    )
    projects.choose_repository(
        project,
        ORDA,
        registry=pinned(root / "re3data"),
        requirements=load_requirements(repositories),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    recorded = projects.summary(project)["repository"]
    return {
        "chosen_repository_name": recorded["repository_name"],
        "chosen_repository_id": ORDA,
        "chosen_re3data_id": ORDA,
    }


def conductor_over(runs: Path, projects: ProjectStore, *agents: Any) -> Conductor:
    conductor = make_conductor(runs, *agents)
    conductor.projects = projects
    return conductor


def in_conversation(
    projects: ProjectStore, project: str, req: InvocationRequest
) -> InvocationRequest:
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    return req.model_copy(update={"conversation_id": conversation})


def stored_input(runs: Path, invocation_id: str) -> dict[str, Any]:
    stored = json.loads((runs / invocation_id / "request.json").read_text())
    found: dict[str, Any] = stored["input"]
    return found


def forged_message() -> InvocationRequest:
    return request("stub.abstain", message().model_copy(update={"project_repository": FORGED}))


def test_a_turn_after_a_choice_is_given_the_chosen_repository(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """Before a choice a turn is told of none, whatever the caller sent; after it, the turn is
    given the repository chosen, in place of what the caller sent."""
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, AbstainingStub())

    before = conductor.invoke(
        in_conversation(projects, project, forged_message()), acting_for=TEST_PRINCIPAL
    )
    assert "project_repository" not in stored_input(runs, before.invocation_id)

    expected = choose(projects, project, tmp_path)
    after = conductor.invoke(
        in_conversation(projects, project, forged_message()), acting_for=TEST_PRINCIPAL
    )
    assert stored_input(runs, after.invocation_id)["project_repository"] == expected


def test_outside_a_project_a_turn_is_told_of_no_repository(
    tmp_path: Path, projects: ProjectStore
) -> None:
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, AbstainingStub())
    for conversation_id in (new_invocation_id(), None):
        req = forged_message().model_copy(update={"conversation_id": conversation_id})
        env = conductor.invoke(req, acting_for=TEST_PRINCIPAL)
        assert "project_repository" not in stored_input(runs, env.invocation_id)


@pytest.mark.requirement("C13.5")
def test_a_hosted_orchestrator_goes_on_without_the_repository_the_profile_keeps(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """The chosen repository is `decisions`: a profile that keeps decisions from a hosted model
    leaves it out of a `Message`, and the turn goes on (invariant 8)."""
    runs = tmp_path / "runs"
    hosted = AbstainingStub()
    hosted.spec = replace(hosted.spec, models=(ModelUse("test", "orchestrator", "hosted"),))
    conductor = conductor_over(runs, projects, hosted)
    choose(projects, project, tmp_path)

    given = conductor.invoke(
        in_conversation(projects, project, request("stub.abstain", message())),
        acting_for=TEST_PRINCIPAL,
    )
    assert stored_input(runs, given.invocation_id)["project_repository"]

    conductor.profile = replace(conductor.profile, hosted_models=frozenset({"inventory"}))
    kept = conductor.invoke(
        in_conversation(projects, project, request("stub.abstain", message())),
        acting_for=TEST_PRINCIPAL,
    )
    assert kept.outcome.status == OutcomeStatus.ABSTAINED, kept.outcome.statement
    assert "project_repository" not in stored_input(runs, kept.invocation_id)


def test_a_class_with_the_mixin_is_given_the_chosen_repository(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """An agent's own class that mixes in `GivenProjectRepository` is given it by slot name, in
    place of the caller's; outside a project the caller's stands."""
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, FactStub())
    expected = choose(projects, project, tmp_path)
    forged = ProbeReading(project_repository=FORGED)

    inside = conductor.invoke(
        in_conversation(projects, project, request("stub.facts", forged)),
        acting_for=TEST_PRINCIPAL,
    )
    assert inside.outcome.status == OutcomeStatus.SUCCEEDED, inside.outcome.statement
    assert stored_input(runs, inside.invocation_id)["project_repository"] == expected

    outside = conductor.invoke(request("stub.facts", forged), acting_for=TEST_PRINCIPAL)
    assert stored_input(runs, outside.invocation_id)["project_repository"] == FORGED.model_dump()

"""An agent's own input class, filled in a project (docs/specs/projects.md, invariant 6): a class
that mixes in `GivenProjectDocuments` or `GivenProjectDecisions` is given the attached documents or
the decided facts by slot name, which the conductor reads from the agent's card, never from the
class's name. The profile's `hosted_models` and `attached_documents` hold as for a core class."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from dd_harness.conductor import Conductor
from dd_harness.projects import FactVerdict, ProjectStore
from dd_harness.testing import (
    TEST_PRINCIPAL,
    FactStub,
    ProbeReading,
    ProbeRecord,
    ScriptedAgent,
    make_conductor,
    request,
)
from dd_harness.testing.plan_storage import plan_fact
from dd_sdk.agent import AgentResult, ModelUse
from dd_sdk.contract.models import (
    GroundingMode,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ProjectDocument,
    ProjectFact,
    ReasonCode,
)

pytestmark = pytest.mark.requirement("C13.3")

PLAN = "Survey responses will be deposited in ORDA under CC BY 4.0."
FUNDER = {"fact_kind": "funder", "fact_subject": "funder", "fact_funder_name": "UKRI"}
FORGED_DOCUMENT = ProjectDocument(
    documentation_name="forged.md",
    documentation_digest="b" * 64,
    documentation_media_type="text/markdown",
    documentation_size=6,
    documentation_added_at=datetime(2026, 11, 1, tzinfo=UTC),
    documentation_text="forged",
)


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project(projects: ProjectStore) -> str:
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Moorland")
    projects.add_documentation(
        project_id, "dmp.md", "text/markdown", PLAN, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    projects.decide_fact(
        project_id, FactVerdict.CHANGED, fact=FUNDER, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    return project_id


def conductor_over(runs: Path, projects: ProjectStore, *agents: Any) -> Conductor:
    conductor = make_conductor(runs, *agents)
    conductor.projects = projects
    return conductor


def in_project(projects: ProjectStore, project: str, req: InvocationRequest) -> InvocationRequest:
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    return req.model_copy(update={"conversation_id": conversation})


def stored_input(runs: Path, invocation_id: str) -> dict[str, Any]:
    stored = json.loads((runs / invocation_id / "request.json").read_text())
    found: dict[str, Any] = stored["input"]
    return found


def forged() -> ProbeReading:
    return ProbeReading(
        project_documents=[FORGED_DOCUMENT],
        project_decisions=[ProjectFact.model_validate({**FUNDER, "fact_funder_name": "Forged"})],
    )


def hosted(stub: FactStub) -> FactStub:
    stub.spec = replace(stub.spec, models=(ModelUse("test", "reader", "hosted"),))
    return stub


def test_a_class_with_the_mixins_is_given_the_documents_and_decisions_in_place_of_its_own(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, FactStub())

    env = conductor.invoke(
        in_project(projects, project, request("stub.facts", forged())), acting_for=TEST_PRINCIPAL
    )

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    given = stored_input(runs, env.invocation_id)
    (document,) = given["project_documents"]
    assert (document["documentation_name"], document["documentation_text"]) == ("dmp.md", PLAN)
    (decision,) = given["project_decisions"]
    assert decision["fact_funder_name"] == FUNDER["fact_funder_name"]


def test_the_document_a_person_marked_as_the_plan_is_given_as_the_plan(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """The conductor says which attached document is the project's data management plan, from
    a person's decision, whatever the caller sent (invariant 32)."""
    notes = projects.add_documentation(
        project,
        "notes.md",
        "text/markdown",
        "Field notes.",
        acted_for=TEST_PRINCIPAL,
        caused_by="t",
    )
    (plan,) = [
        d["documentation_digest"]
        for d in projects.documentation(project)
        if d["documentation_name"] == "dmp.md"
    ]
    projects.decide_fact(
        project,
        FactVerdict.CHANGED,
        fact=plan_fact(plan),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, FactStub())
    sent = ProbeReading(
        project_documents=[FORGED_DOCUMENT.model_copy(update={"documentation_is_plan": True})]
    )

    env = conductor.invoke(
        in_project(projects, project, request("stub.facts", sent)), acting_for=TEST_PRINCIPAL
    )

    given = stored_input(runs, env.invocation_id)
    marked = {
        d["documentation_digest"]: d.get("documentation_is_plan")
        for d in given["project_documents"]
    }
    assert marked == {plan: True, notes: None}


def test_outside_a_project_the_caller_gives_its_own_as_to_a_drafter(
    tmp_path: Path, projects: ProjectStore
) -> None:
    """What a caller sends outside a project is not the project's, as for a `DraftRequest`."""
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, FactStub())
    env = conductor.invoke(request("stub.facts", forged()), acting_for=TEST_PRINCIPAL)
    given = stored_input(runs, env.invocation_id)
    (document,) = given["project_documents"]
    assert document["documentation_name"] == FORGED_DOCUMENT.documentation_name


def test_a_class_without_the_mixins_is_not_filled(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    runs = tmp_path / "runs"
    declined = AgentResult(
        outcome=Outcome(
            status=OutcomeStatus.ABSTAINED,
            reason_code=ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
            statement="Not scripted.",
        )
    )
    conductor = conductor_over(runs, projects, ScriptedAgent(GroundingMode.NONE, declined))
    env = conductor.invoke(
        in_project(projects, project, request("fake.none", ProbeRecord(title="Moorland"))),
        acting_for=TEST_PRINCIPAL,
    )
    given = stored_input(runs, env.invocation_id)
    assert "project_documents" not in given
    assert "project_decisions" not in given


@pytest.mark.requirement("C13.5")
def test_a_hosted_model_is_given_the_decisions_but_not_the_documents_by_default(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """Documents are `documentation`, which the default `hosted_models` keeps from a hosted model:
    they are left out and the run goes on, as for a drafter (invariant 8)."""
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, hosted(FactStub()))
    env = conductor.invoke(
        in_project(projects, project, request("stub.facts", ProbeReading())),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    given = stored_input(runs, env.invocation_id)
    assert "project_documents" not in given
    assert given["project_decisions"]


@pytest.mark.requirement("C13.5")
def test_a_profile_may_let_a_hosted_model_read_the_documents(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, hosted(FactStub()))
    conductor.profile = replace(
        conductor.profile, hosted_models=conductor.profile.hosted_models | {"documentation"}
    )
    env = conductor.invoke(
        in_project(projects, project, request("stub.facts", ProbeReading())),
        acting_for=TEST_PRINCIPAL,
    )
    assert stored_input(runs, env.invocation_id)["project_documents"]


def test_a_profile_that_refuses_attached_documents_gives_none(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, FactStub())
    conductor.profile = replace(conductor.profile, attached_documents="refused")
    env = conductor.invoke(
        in_project(projects, project, request("stub.facts", forged())), acting_for=TEST_PRINCIPAL
    )
    given = stored_input(runs, env.invocation_id)
    assert "project_documents" not in given
    assert given["project_decisions"]

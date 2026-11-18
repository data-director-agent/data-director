"""Facts a person decided, in runs (docs/specs/projects.md, invariants 6 and 8): an agent's proposed
facts are recorded from a payload of any class, never given to an agent until a person decides
them, and then given to every drafter and orchestrator in the project as `project_decisions`."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from dd_harness.conductor import Conductor
from dd_harness.projects import FACT_PROPOSED, FactVerdict, ProjectStore
from dd_harness.testing import (
    TEST_PRINCIPAL,
    AbstainingStub,
    DocumentStub,
    FactStub,
    make_conductor,
    message,
    request,
)
from dd_sdk.agent import ModelUse
from dd_sdk.contract.models import (
    DocumentKind,
    DraftRequest,
    FileInventory,
    IdentificationMethod,
    InventoryFile,
    InvocationRequest,
    OpenInput,
    OutcomeStatus,
    ProjectFact,
    new_invocation_id,
)

pytestmark = pytest.mark.requirement("C13.3")

THUMBS = {
    "fact_kind": "file_inclusion",
    "fact_subject": "data/Thumbs.db",
    "fact_file_path": "data/Thumbs.db",
    "file_decision": "exclude",
    "fact_check_kind": "system_file",
    "proposed_because": "A Windows thumbnail cache, not part of the data.",
}
FORGED = {
    "fact_kind": "licence",
    "fact_subject": "licence",
    "licence_id": "CC0-1.0",
}


def inventory() -> FileInventory:
    return FileInventory(
        inventory_tool="dd-inventory",
        inventory_tool_version="0.1.0",
        inventory_made_at=datetime(2026, 10, 30, tzinfo=UTC),
        inventory_files=[
            InventoryFile(
                file_path=path,
                file_size=10,
                file_sha256="a" * 64,
                file_media_type="text/csv",
                file_pronom_ids=[],
                file_identified_by=IdentificationMethod.EXTENSION,
            )
            for path in ("data/readings.csv", "data/Thumbs.db")
        ],
    )


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project(projects: ProjectStore) -> str:
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Moorland")
    projects.add_inventory(
        project_id,
        inventory().model_dump(mode="json", exclude_none=True),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    return project_id


def conductor_over(runs: Path, projects: ProjectStore, *agents: Any) -> Conductor:
    conductor = make_conductor(runs, *agents)
    conductor.projects = projects
    return conductor


def in_conversation(req: InvocationRequest, conversation_id: str) -> InvocationRequest:
    return req.model_copy(update={"conversation_id": conversation_id})


def stored_input(runs: Path, invocation_id: str) -> dict[str, Any]:
    stored = json.loads((runs / invocation_id / "request.json").read_text())
    found: dict[str, Any] = stored["input"]
    return found


def draft(**facts: Any) -> DraftRequest:
    return DraftRequest(document_kind=DocumentKind.README, **facts)


def test_a_proposal_from_any_payload_is_recorded_and_given_once_decided(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """A checking agent's proposals are recorded, caused by its run, from a payload class the
    harness knows only by its card. A drafter is given none of them until a person decides, and
    then the fact without the agent's words about why."""
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, FactStub(THUMBS), DocumentStub())
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")

    checked = conductor.invoke(
        in_conversation(
            request("stub.facts", OpenInput.model_validate({"schema_class": "FileInventory"})),
            conversation,
        ),
        acting_for=TEST_PRINCIPAL,
    )
    assert checked.outcome.status == OutcomeStatus.SUCCEEDED, checked.outcome.statement
    proposed = [e for e in projects.events(project) if e["event"] == FACT_PROPOSED]
    assert [(e["caused_by"], e["agent_id"]) for e in proposed] == [
        (checked.invocation_id, "stub.facts")
    ]

    drafted = conductor.invoke(
        in_conversation(request("stub.document", draft()), conversation),
        acting_for=TEST_PRINCIPAL,
    )
    assert "project_decisions" not in stored_input(runs, drafted.invocation_id)

    (offered,) = projects.proposals(project)
    projects.decide_fact(
        project,
        FactVerdict.CONFIRMED,
        proposal=offered["proposal"],
        acted_for=TEST_PRINCIPAL,
        caused_by="t",
    )
    drafted = conductor.invoke(
        in_conversation(
            request("stub.document", draft(project_decisions=[ProjectFact.model_validate(FORGED)])),
            conversation,
        ),
        acting_for=TEST_PRINCIPAL,
    )
    assert drafted.outcome.status == OutcomeStatus.SUCCEEDED, drafted.outcome.statement
    (given,) = stored_input(runs, drafted.invocation_id)["project_decisions"]
    assert given["fact_subject"] == THUMBS["fact_subject"]
    assert given["file_decision"] == "exclude"
    assert "proposed_because" not in given


def test_a_message_is_given_the_decisions_only_in_a_project(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """A `Message`'s `project_decisions` are the conductor's: a caller's are replaced in a
    project and removed outside one."""
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, AbstainingStub())
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    forged = message().model_copy(
        update={"project_decisions": [ProjectFact.model_validate(FORGED)]}
    )

    for conversation_id in (conversation, new_invocation_id(), None):
        req = request("stub.abstain", forged).model_copy(
            update={"conversation_id": conversation_id}
        )
        env = conductor.invoke(req, acting_for=TEST_PRINCIPAL)
        assert "project_decisions" not in stored_input(runs, env.invocation_id)

    projects.decide_fact(
        project, FactVerdict.CHANGED, fact=THUMBS, acted_for=TEST_PRINCIPAL, caused_by="t"
    )
    env = conductor.invoke(
        in_conversation(request("stub.abstain", forged), conversation), acting_for=TEST_PRINCIPAL
    )
    (given,) = stored_input(runs, env.invocation_id)["project_decisions"]
    assert given["fact_kind"] == "file_inclusion"


@pytest.mark.requirement("C13.5")
@pytest.mark.parametrize(
    ("hosted_models", "status"),
    [
        (None, OutcomeStatus.SUCCEEDED),
        (frozenset({"inventory"}), OutcomeStatus.FAILED),
    ],
)
def test_decisions_go_to_a_hosted_model_unless_the_profile_keeps_them(
    tmp_path: Path,
    projects: ProjectStore,
    project: str,
    hosted_models: frozenset[str] | None,
    status: OutcomeStatus,
) -> None:
    """Decided facts are `decisions`, which the default `hosted_models` allows. A profile that
    keeps them from a hosted model refuses the run rather than draft as if nothing had been
    decided (docs/specs/projects.md, invariant 8)."""
    conductor = conductor_over(
        tmp_path / "runs", projects, DocumentStub("hosted-model", hosting="hosted")
    )
    if hosted_models is not None:
        conductor.profile = replace(conductor.profile, hosted_models=hosted_models)
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    projects.decide_fact(
        project, FactVerdict.CHANGED, fact=THUMBS, acted_for=TEST_PRINCIPAL, caused_by="t"
    )

    env = conductor.invoke(
        in_conversation(request("stub.document", draft()), conversation),
        acting_for=TEST_PRINCIPAL,
    )

    assert env.outcome.status == status, env.outcome.statement
    if status == OutcomeStatus.FAILED:
        assert env.problem is not None
        assert str(env.problem.type).endswith("project-content-withheld")


@pytest.mark.requirement("C13.5")
def test_a_hosted_orchestrator_goes_on_without_the_decisions_the_profile_keeps(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """A `Message`'s decided facts that the profile keeps from a hosted model are left out, not
    refused: an orchestrator drafts nothing, so a conversation does not stop once a fact is
    decided (docs/specs/projects.md, invariant 8)."""
    runs = tmp_path / "runs"
    hosted = AbstainingStub()
    hosted.spec = replace(hosted.spec, models=(ModelUse("test", "orchestrator", "hosted"),))
    conductor = conductor_over(runs, projects, hosted)
    conductor.profile = replace(conductor.profile, hosted_models=frozenset({"inventory"}))
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    projects.decide_fact(
        project, FactVerdict.CHANGED, fact=THUMBS, acted_for=TEST_PRINCIPAL, caused_by="t"
    )

    env = conductor.invoke(
        in_conversation(request("stub.abstain", message()), conversation),
        acting_for=TEST_PRINCIPAL,
    )

    assert env.problem is None or not str(env.problem.type).endswith("project-content-withheld")
    assert env.outcome.status == OutcomeStatus.ABSTAINED, env.outcome.statement
    assert "project_decisions" not in stored_input(runs, env.invocation_id)

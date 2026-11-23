"""The project's metadata record, given to an agent's own class (docs/specs/projects.md,
invariants 6 and 8; #432): a class that mixes in `GivenProjectMetadataRecord` is given the latest
version of the metadata record, whatever its state, and the version a person approved last, by
slot name. Only the conductor fills them in a project; outside one, the caller's are kept. Both are
`documentation`, so a profile that keeps documentation from a hosted model refuses the run. A class
that mixes in `GivenProjectPlan` is given the data management plan written in the project, as a
person approved it last, the same way."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from dd_harness.conductor import Conductor
from dd_harness.projects import APPROVED, Decision, ProjectStore
from dd_harness.testing import (
    TEST_PRINCIPAL,
    DocumentStub,
    FactStub,
    ProbeReading,
    document_request,
    make_conductor,
    request,
)
from dd_sdk.agent import ModelUse
from dd_sdk.contract.models import (
    CurrentVersion,
    DocumentKind,
    DocumentVersionRef,
    InvocationRequest,
    OutcomeStatus,
    VersionState,
)

pytestmark = pytest.mark.requirement("C13.3")

FORGED_ID = "01900000-0000-7000-8000-000000000000"
FORGED = CurrentVersion(
    version_ref=DocumentVersionRef(document_id=FORGED_ID, version=1),
    media_type="application/json",
    document_text="{}",
    version_state=VersionState.APPROVED,
)


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project(projects: ProjectStore) -> str:
    return projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Peatland")


def draft_record(
    projects: ProjectStore,
    project: str,
    *,
    approve: bool,
    kind: DocumentKind = DocumentKind.METADATA_RECORD,
) -> DocumentVersionRef:
    """A document drafted into the project by the document stub, a metadata record unless asked
    otherwise, approved if asked."""
    drafter = make_conductor(Path(projects.root).parent / "draft-runs", DocumentStub())
    env = drafter.invoke(
        request("stub.document", document_request(kind)),
        acting_for=TEST_PRINCIPAL,
    )
    ref = projects.record_draft(project, env)
    if approve:
        (digest,) = [
            d["versions"][-1]["digest"]
            for d in projects.documents(project)
            if d["document_id"] == ref.document_id
        ]
        projects.decide(
            project,
            Decision(ref.document_id, ref.version, digest, APPROVED),
            acted_for=TEST_PRINCIPAL,
            caused_by="test",
        )
    return ref


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


def test_the_latest_draft_and_the_approved_version_are_given_in_place_of_the_callers(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    approved = draft_record(projects, project, approve=True)
    latest = draft_record(projects, project, approve=False)
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, FactStub())

    env = conductor.invoke(
        in_project(
            projects, project, request("stub.facts", ProbeReading(project_metadata_draft=FORGED))
        ),
        acting_for=TEST_PRINCIPAL,
    )

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    given = stored_input(runs, env.invocation_id)
    draft = given["project_metadata_draft"]
    assert draft["version_ref"] == latest.model_dump(mode="json")
    assert draft["version_state"] == VersionState.PROPOSED.value
    assert draft["document_text"]
    assert given["project_metadata_approved"]["version_ref"] == approved.model_dump(mode="json")


def test_the_plan_a_person_approved_last_is_given_and_a_draft_alone_is_not(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, FactStub())

    def given_plan() -> Any:
        env = conductor.invoke(
            in_project(projects, project, request("stub.facts", ProbeReading())),
            acting_for=TEST_PRINCIPAL,
        )
        assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
        return stored_input(runs, env.invocation_id).get("project_plan_approved")

    draft_record(projects, project, approve=False, kind=DocumentKind.DMP)
    assert given_plan() is None
    approved = draft_record(projects, project, approve=True, kind=DocumentKind.DMP)
    draft_record(projects, project, approve=False, kind=DocumentKind.DMP)
    plan = given_plan()
    assert plan["version_ref"] == approved.model_dump(mode="json")
    assert plan["document_text"]


def test_a_project_without_a_metadata_record_gives_neither(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, FactStub())
    env = conductor.invoke(
        in_project(
            projects, project, request("stub.facts", ProbeReading(project_metadata_draft=FORGED))
        ),
        acting_for=TEST_PRINCIPAL,
    )
    given = stored_input(runs, env.invocation_id)
    assert "project_metadata_draft" not in given
    assert "project_metadata_approved" not in given


def test_outside_a_project_the_callers_record_is_kept(
    tmp_path: Path, projects: ProjectStore
) -> None:
    runs = tmp_path / "runs"
    conductor = conductor_over(runs, projects, FactStub())
    env = conductor.invoke(
        request("stub.facts", ProbeReading(project_metadata_draft=FORGED)),
        acting_for=TEST_PRINCIPAL,
    )
    given = stored_input(runs, env.invocation_id)
    assert given["project_metadata_draft"]["version_ref"]["document_id"] == FORGED_ID


def test_a_hosted_model_is_refused_the_record_by_default(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """The record is documentation, refused rather than left out, as a drafter's is."""
    draft_record(projects, project, approve=False)
    stub = FactStub()
    stub.spec = replace(stub.spec, models=(ModelUse("test", "reader", "hosted"),))
    conductor = conductor_over(tmp_path / "runs", projects, stub)
    env = conductor.invoke(
        in_project(projects, project, request("stub.facts", ProbeReading())),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.FAILED

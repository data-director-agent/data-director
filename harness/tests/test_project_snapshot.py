"""A project's facts come from one read of its log per invocation (docs/specs/storage.md,
invariant 12): the conductor reads the log through a snapshot (`Projects.snapshot`), which answers
as the store does and takes no change."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from requirement_sets import ORDA, override, pinned, standard, write

from dd_harness.conductor import Conductor
from dd_harness.projects import TITLE_BY_RESEARCHER, ProjectStore, UnknownProjectError
from dd_harness.requirements import load_requirements
from dd_harness.storage import ProjectLog
from dd_harness.testing import (
    TEST_PRINCIPAL,
    AbstainingStub,
    DocumentStub,
    make_conductor,
    message,
    request,
)
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import (
    DocumentKind,
    DraftRequest,
    Envelope,
    FileInventory,
    IdentificationMethod,
    InventoryFile,
    InvocationRequest,
)


class CountingLog:
    """A `ProjectLog` that counts how often each project's events are read."""

    def __init__(self, log: ProjectLog) -> None:
        self.inner = log
        self.reads = 0

    def events(self, project_id: str) -> list[dict[str, Any]]:
        self.reads += 1
        return self.inner.events(project_id)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


class Counted:
    """An agent that notes how often the project log had been read when it was run."""

    def __init__(self, agent: Any, log: CountingLog) -> None:
        self.agent, self.log = agent, log
        self.spec = agent.spec
        self.reads_before_run: list[int] = []
        self.envelope: Envelope | None = None
        self.stored: dict[str, Any] | None = None

    def run(self, req: InvocationRequest, ctx: RunContext) -> AgentResult:
        self.reads_before_run.append(self.log.reads)
        result: AgentResult = self.agent.run(req, ctx)
        return result


def inventory() -> dict[str, Any]:
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
                file_identified_by=IdentificationMethod.EXTENSION,
            )
            for path in ("a.csv", "b.csv")
        ],
    ).model_dump(mode="json", exclude_none=True)


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project(projects: ProjectStore, tmp_path: Path) -> str:
    """A project with an inventory and ORDA chosen."""
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil")
    projects.add_inventory(project_id, inventory(), acted_for=TEST_PRINCIPAL, caused_by="test")
    repositories = write(
        tmp_path / "repositories", ("standards", standard()), ("overrides", override())
    )
    projects.choose_repository(
        project_id,
        ORDA,
        registry=pinned(tmp_path / "re3data"),
        requirements=load_requirements(repositories),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    return project_id


def counted_run(
    tmp_path: Path, projects: ProjectStore, project: str, agent: Any, agent_id: str, input_: Any
) -> Counted:
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    log = CountingLog(projects.log)
    projects.log = log
    counted = Counted(agent, log)
    conductor: Conductor = make_conductor(tmp_path / "runs", counted)
    conductor.projects = projects
    counted.envelope = conductor.invoke(
        request(agent_id, input_).model_copy(update={"conversation_id": conversation}),
        acting_for=TEST_PRINCIPAL,
    )
    counted.stored = conductor.store.get_request(counted.envelope.invocation_id)
    return counted


def test_a_message_in_a_project_reads_the_log_once_before_its_agent_runs(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    counted = counted_run(tmp_path, projects, project, AbstainingStub(), "stub.abstain", message())
    assert counted.reads_before_run == [1]


def test_a_draft_in_a_project_reads_the_log_once_before_its_agent_runs(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    draft = DraftRequest(document_kind=DocumentKind.README)
    counted = counted_run(tmp_path, projects, project, DocumentStub(), "stub.document", draft)
    assert counted.reads_before_run == [1]


def test_a_snapshot_answers_as_the_store_does(projects: ProjectStore, project: str) -> None:
    snapshot = projects.snapshot(project)
    assert snapshot.exists(project)
    assert snapshot.events(project) == projects.events(project)
    assert snapshot.summary(project) == projects.summary(project)
    assert snapshot.inventory(project) == projects.inventory(project)
    assert snapshot.requirements(project) == projects.requirements(project)
    assert snapshot.progress(project) == projects.progress(project)
    assert snapshot.researchers(project) == projects.researchers(project)
    assert snapshot.is_deleted(project) is False


def test_a_snapshot_reads_the_log_once_and_keeps_what_it_read(
    projects: ProjectStore, project: str
) -> None:
    log = CountingLog(projects.log)
    projects.log = log
    snapshot = projects.snapshot(project)
    snapshot.summary(project)
    snapshot.inventory(project)
    snapshot.progress(project)
    assert log.reads == 1
    # A change made after the snapshot was read is the store's, and not the snapshot's.
    projects.rename(
        project, "Peat", source=TITLE_BY_RESEARCHER, acted_for=TEST_PRINCIPAL, caused_by="t"
    )
    assert snapshot.summary(project)["title"] == "Soil"
    assert projects.summary(project)["title"] == "Peat"


def test_a_snapshot_takes_no_change(projects: ProjectStore, project: str) -> None:
    snapshot = projects.snapshot(project)
    with pytest.raises(TypeError):
        snapshot.add_inventory(project, inventory(), acted_for=TEST_PRINCIPAL, caused_by="t")
    with pytest.raises(TypeError):
        snapshot.rename(
            project, "Peat", source=TITLE_BY_RESEARCHER, acted_for=TEST_PRINCIPAL, caused_by="t"
        )
    assert projects.summary(project)["title"] == "Soil"


@pytest.mark.parametrize("project_id", ["0190a3e4-0000-7000-8000-000000000000", "not-a-project"])
def test_a_snapshot_of_no_project_names_none(projects: ProjectStore, project_id: str) -> None:
    snapshot = projects.snapshot(project_id)
    assert not snapshot.exists(project_id)
    with pytest.raises(UnknownProjectError):
        snapshot.summary(project_id)


def test_a_snapshot_names_only_its_own_project(projects: ProjectStore, project: str) -> None:
    other = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Other")
    snapshot = projects.snapshot(project)
    assert not snapshot.exists(other)
    with pytest.raises(UnknownProjectError):
        snapshot.summary(other)


def test_a_message_is_told_the_inventory_digest_its_project_recorded(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    counted = counted_run(tmp_path, projects, project, AbstainingStub(), "stub.abstain", message())
    stored = counted.stored
    added = next(e for e in projects.events(project) if e["event"] == "inventory_added")
    assert stored is not None
    assert stored["input"]["project_inventory"]["inventory_digest"] == added["digest"]
    assert stored["input"]["project_inventory"]["inventory_file_count"] == added["file_count"]

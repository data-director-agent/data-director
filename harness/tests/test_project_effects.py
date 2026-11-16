"""What a finished run does to its project, behind `ProjectEffects` (docs/specs/projects.md):
a draft becomes a proposed version, a model's title and entry point are recorded unless a person
has given theirs, and a deleted project still records a draft but takes no title or entry point."""

from __future__ import annotations

from pathlib import Path

import pytest

from dd_harness.progress import ENTRY_BY_MODEL, ENTRY_BY_RESEARCHER, ENTRY_CHOSEN
from dd_harness.project_effects import ProjectEffects
from dd_harness.projects import (
    DOCUMENT_VERSION_ADDED,
    PROJECT_RENAMED,
    TITLE_BY_MODEL,
    TITLE_BY_RESEARCHER,
    ProjectStore,
)
from dd_harness.storage import ProjectStorage
from dd_harness.testing import TEST_PRINCIPAL
from dd_harness.testing.storage import drafted_readme
from dd_sdk.contract.models import (
    Derivation,
    DocumentVersionRef,
    Envelope,
    Outcome,
    OutcomeStatus,
    Reply,
    new_invocation_id,
)


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture(scope="module")
def draft() -> Envelope:
    return drafted_readme()


def _in(envelope: Envelope, project_id: str | None) -> Envelope:
    """The run as if it had gone in the project, with a fresh invocation id."""
    return envelope.model_copy(
        update={"project_id": project_id, "invocation_id": new_invocation_id()}
    )


def _reply(draft: Envelope, project_id: str, **named: object) -> Envelope:
    """A succeeded `Reply` in the project naming what `named` gives it."""
    payload = Reply(reply_text="Noted.", reply_derivation=Derivation.TEMPLATE, **named)
    return _in(draft, project_id).model_copy(update={"payload": payload, "payload_schema": None})


def _events(store: ProjectStore, project_id: str, kind: str) -> list[dict[str, object]]:
    return [e for e in store.events(project_id) if e["event"] == kind]


def test_the_project_rules_are_the_conductors_project_effects(store: ProjectStore) -> None:
    effects: ProjectEffects = store
    storage: ProjectStorage = store
    assert effects is storage


def test_a_draft_becomes_a_proposed_version_caused_by_its_run(
    store: ProjectStore, draft: Envelope
) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    run = _in(draft, project_id)
    assert store.after_run(run, acted_for=TEST_PRINCIPAL) is None
    [added] = _events(store, project_id, DOCUMENT_VERSION_ADDED)
    assert added["caused_by"] == run.invocation_id
    assert [d["versions"][0]["state"] for d in store.documents(project_id)] == ["proposed"]


def test_a_draft_the_project_refuses_is_reported_and_records_nothing(
    store: ProjectStore, draft: Envelope
) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    assert draft.payload is not None
    revises = DocumentVersionRef(document_id=new_invocation_id(), version=1)
    run = _in(draft, project_id).model_copy(
        update={"payload": draft.payload.model_copy(update={"revises": revises})}
    )
    assert store.after_run(run, acted_for=TEST_PRINCIPAL)
    assert _events(store, project_id, DOCUMENT_VERSION_ADDED) == []


def test_a_run_that_did_not_succeed_or_is_in_no_project_has_no_effect(
    store: ProjectStore, draft: Envelope
) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    before = store.events(project_id)
    failed = _in(draft, project_id).model_copy(
        update={"outcome": Outcome(status=OutcomeStatus.FAILED, statement="No.")}
    )
    assert store.after_run(failed, acted_for=TEST_PRINCIPAL) is None
    assert store.after_run(_in(draft, None), acted_for=TEST_PRINCIPAL) is None
    assert store.events(project_id) == before


def test_a_models_title_names_the_project_until_a_person_has(
    store: ProjectStore, draft: Envelope
) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    run = _reply(draft, project_id, new_project_title="Soil cores")
    assert store.after_run(run, acted_for=TEST_PRINCIPAL) is None
    [renamed] = _events(store, project_id, PROJECT_RENAMED)
    assert renamed["caused_by"] == run.invocation_id
    assert store.summary(project_id)["title_source"] == TITLE_BY_MODEL

    named = store.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Mine")
    store.after_run(_reply(draft, named, new_project_title="Theirs"), acted_for=TEST_PRINCIPAL)
    summary = store.summary(named)
    assert (summary["title"], summary["title_source"]) == ("Mine", TITLE_BY_RESEARCHER)


def test_a_models_entry_point_is_recorded_until_the_researcher_chooses_one(
    store: ProjectStore, draft: Envelope
) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    run = _reply(draft, project_id, new_project_entry=2)
    assert store.after_run(run, acted_for=TEST_PRINCIPAL) is None
    [chosen] = _events(store, project_id, ENTRY_CHOSEN)
    assert (chosen["entry_source"], chosen["caused_by"]) == (ENTRY_BY_MODEL, run.invocation_id)

    store.choose_entry(
        project_id, 1, acted_for=TEST_PRINCIPAL, caused_by="test", source=ENTRY_BY_RESEARCHER
    )
    store.after_run(_reply(draft, project_id, new_project_entry=3), acted_for=TEST_PRINCIPAL)
    sources = [e["entry_source"] for e in _events(store, project_id, ENTRY_CHOSEN)]
    assert sources == [ENTRY_BY_MODEL, ENTRY_BY_RESEARCHER]


def test_a_deleted_project_keeps_a_draft_but_takes_no_title_or_entry_point(
    store: ProjectStore, draft: Envelope
) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    store.delete(project_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    reply = _reply(draft, project_id, new_project_title="Late", new_project_entry=2)
    assert store.after_run(reply, acted_for=TEST_PRINCIPAL) is None
    assert store.after_run(_in(draft, project_id), acted_for=TEST_PRINCIPAL) is None
    assert _events(store, project_id, PROJECT_RENAMED) == []
    assert _events(store, project_id, ENTRY_CHOSEN) == []
    assert len(_events(store, project_id, DOCUMENT_VERSION_ADDED)) == 1

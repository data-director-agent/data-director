"""Where a project is in the process flow, derived from its log and never stored
(docs/specs/orchestration.md, `dd_harness.progress`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dd_harness import progress
from dd_harness.projects import (
    DOCUMENT_VERSION_ADDED,
    DOCUMENT_VERSION_DECIDED,
    INVENTORY_ADDED,
    REPOSITORY_CHOSEN,
    ProjectError,
    ProjectStore,
)
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.process_flow import OUT_OF_SCOPE


def added(document_id: str, kind: str) -> dict[str, Any]:
    return {"event": DOCUMENT_VERSION_ADDED, "document_id": document_id, "document_kind": kind}


def decided(document_id: str, decision: str = "approved") -> dict[str, Any]:
    return {"event": DOCUMENT_VERSION_DECIDED, "document_id": document_id, "decision": decision}


def marked(step_id: str, mark: str) -> dict[str, Any]:
    return {"event": progress.STEP_MARKED, "step_id": step_id, "mark": mark}


def test_the_event_names_are_the_project_logs() -> None:
    assert progress.INVENTORY_ADDED == INVENTORY_ADDED
    assert progress.REPOSITORY_CHOSEN == REPOSITORY_CHOSEN
    assert progress.DOCUMENT_VERSION_ADDED == DOCUMENT_VERSION_ADDED
    assert progress.DOCUMENT_VERSION_DECIDED == DOCUMENT_VERSION_DECIDED


def test_an_empty_log_shows_every_step_open() -> None:
    assert progress.step_states([]) == {}
    assert progress.entry_chosen([]) is None


def test_what_the_log_produces_shows_its_step_whatever_the_order() -> None:
    # The repository chosen before the files are described: work out of order still counts.
    states = progress.step_states(
        [{"event": REPOSITORY_CHOSEN}, {"event": INVENTORY_ADDED}, added("m", "metadata_record")]
    )
    assert states == {
        "repository.recommend": "done",
        "preparation.files": "done",
        "preparation.metadata": "started",
    }
    # In flow order, not log order.
    assert list(states) == ["repository.recommend", "preparation.files", "preparation.metadata"]


def test_a_document_step_is_done_once_what_it_needs_and_all_else_drafted_is_approved() -> None:
    # A README alone is enough where there is no table, so no data dictionary.
    readme = [added("r", "readme"), decided("r")]
    assert progress.step_states(readme)["preparation.documentation"] == "done"
    # A data dictionary alone is not.
    dictionary = [added("d", "data_dictionary"), decided("d")]
    assert progress.step_states(dictionary)["preparation.documentation"] == "started"
    # One drafted is approved before the step is done.
    events = [*readme, added("d", "data_dictionary")]
    assert progress.step_states(events)["preparation.documentation"] == "started"
    assert (
        progress.step_states([*events, decided("d", "rejected")])["preparation.documentation"]
        == "started"
    )
    assert progress.step_states([*events, decided("d")])["preparation.documentation"] == "done"


def test_a_researcher_marks_a_step_and_may_take_the_mark_back() -> None:
    assert progress.step_states([marked("governance.embargo", "skipped")]) == {
        "governance.embargo": "skipped"
    }
    assert progress.step_states([marked("governance.embargo", "done")]) == {
        "governance.embargo": "done"
    }
    assert (
        progress.step_states(
            [marked("governance.embargo", "skipped"), marked("governance.embargo", "open")]
        )
        == {}
    )


def test_what_the_log_produced_outranks_a_skip_and_a_mark_may_finish_a_started_step() -> None:
    assert (
        progress.step_states([{"event": INVENTORY_ADDED}, marked("preparation.files", "open")])[
            "preparation.files"
        ]
        == "done"
    )
    assert (
        progress.step_states([{"event": INVENTORY_ADDED}, marked("preparation.files", "skipped")])[
            "preparation.files"
        ]
        == "done"
    )
    assert (
        progress.step_states(
            [added("m", "metadata_record"), marked("preparation.metadata", "done")]
        )["preparation.metadata"]
        == "done"
    )


def test_the_entry_point_chosen_last_counts() -> None:
    events = [{"event": progress.ENTRY_CHOSEN, "entry": n} for n in (2, 3, 2)]
    assert progress.entry_chosen(events) == 2


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


def test_the_store_records_the_researchers_word_and_derives_progress(store: ProjectStore) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    store.choose_entry(project, 3, acted_for=TEST_PRINCIPAL, caused_by="test")
    store.mark_step(project, "repository.mandated", "done", acted_for=TEST_PRINCIPAL, caused_by="t")
    assert store.progress(project) == {
        "entry": 3,
        "steps": {"repository.mandated": "done"},
        "suggested": "repository.recommend",
    }
    assert store.summary(project)["progress"] == store.progress(project)


def test_the_store_refuses_what_is_no_entry_step_or_mark(store: ProjectStore) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    before = store.events(project)
    with pytest.raises(ProjectError):
        store.choose_entry(project, 4, acted_for=TEST_PRINCIPAL, caused_by="test")
    for step_id, mark in (
        ("R5", "done"),
        (next(iter(OUT_OF_SCOPE)), "done"),
        ("governance.embargo", "maybe"),
    ):
        with pytest.raises(ProjectError):
            store.mark_step(project, step_id, mark, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert store.events(project) == before

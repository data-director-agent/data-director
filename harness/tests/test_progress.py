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
    PACKAGE_BUILT,
    PROJECT_VALIDATED,
    REPOSITORY_CHOSEN,
    ProjectError,
    ProjectStore,
)
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.intake import NO, NOT_SURE, YES, question


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
    assert progress.PROJECT_VALIDATED == PROJECT_VALIDATED
    assert progress.PACKAGE_BUILT == PACKAGE_BUILT


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


def validated(conforms: bool) -> dict[str, Any]:
    return {"event": PROJECT_VALIDATED, "conforms": conforms}


def test_the_last_validation_decides_the_validate_step_and_a_package_finalises() -> None:
    assert progress.step_states([validated(False)]) == {"deposit.validate": "started"}
    assert progress.step_states([validated(False), validated(True)]) == {"deposit.validate": "done"}
    # A validation that fails after a pass shows the step begun again: the files or documents
    # changed since.
    assert progress.step_states([validated(True), validated(False)]) == {
        "deposit.validate": "started"
    }
    assert progress.step_states([validated(True), {"event": PACKAGE_BUILT}]) == {
        "deposit.validate": "done",
        "deposit.finalise": "done",
    }


def test_a_document_step_is_done_once_what_it_needs_and_all_else_drafted_is_approved() -> None:
    # A README alone is enough where there is no table, so no data dictionary.
    readme = [{"event": INVENTORY_ADDED}, added("r", "readme"), decided("r")]
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


def test_a_readme_drafted_before_the_inventory_plans_the_documentation() -> None:
    """Before the data are collected a README plans the documentation (#1017): its versions show
    `setup.documentation`, not `preparation.documentation`, which a README drafted once the
    inventory is added shows."""
    planned = [added("r", "readme")]
    assert progress.step_states(planned) == {"setup.documentation": "started"}
    approved = [*planned, decided("r")]
    assert progress.step_states(approved) == {"setup.documentation": "done"}
    # The same README drafted again once the data exist shows the later step, and the plan's
    # approval still counts for the first.
    later = [*approved, {"event": INVENTORY_ADDED}, added("r", "readme")]
    states = progress.step_states(later)
    assert states["setup.documentation"] == "done"
    assert states["preparation.documentation"] == "started"
    assert progress.step_states([*later, decided("r")])["preparation.documentation"] == "done"


def test_an_approved_data_management_plan_finishes_writing_one() -> None:
    plan = [added("p", "dmp")]
    assert progress.step_states(plan)["setup.dmp-create"] == "started"
    assert progress.step_states([*plan, decided("p")])["setup.dmp-create"] == "done"


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


def test_an_entry_point_with_no_source_is_the_researchers() -> None:
    old = [{"event": progress.ENTRY_CHOSEN, "entry": 2}]
    assert progress.entry_and_source(old) == (2, progress.ENTRY_BY_RESEARCHER)
    assert progress.entry_and_source([]) == (None, None)


def test_with_no_entry_point_nothing_open_is_suggested() -> None:
    """A researcher who has not said where they are is not sent to Phase 1."""
    assert progress.describe([])["suggested"] is None
    assert progress.describe([])["entry_source"] is None


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


def test_the_store_records_the_researchers_word_and_derives_progress(store: ProjectStore) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    store.choose_entry(project, 3, acted_for=TEST_PRINCIPAL, caused_by="test")
    store.mark_step(project, "repository.mandated", "done", acted_for=TEST_PRINCIPAL, caused_by="t")
    found = store.progress(project)
    assert {k: found[k] for k in ("entry", "entry_source", "steps", "suggested")} == {
        "entry": 3,
        "entry_source": "researcher",
        "steps": {"repository.mandated": "done"},
        "suggested": "repository.recommend",
    }
    # Each state says why, with when the log recorded it.
    reason = found["reasons"]["repository.mandated"]
    assert reason["source"] == "marked" and reason["state"] == "done" and reason["at"]
    assert store.summary(project)["progress"] == store.progress(project)


def test_the_store_suggests_a_step_the_deployments_agents_serve(store: ProjectStore) -> None:
    """With the deployment's agents given, the summary, the progress, the intake and a snapshot
    all suggest the Phase 1 step an agent serves, not the one none does (#1377)."""
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    store.choose_entry(project, 1, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert store.progress(project)["suggested"] == "setup.documentation"
    assert store.progress(project)["passed_over"] == []
    store.serving = lambda: [{"agent_id": "advisor.standards", "serves": ["setup.formats"]}]
    assert store.progress(project)["suggested"] == "setup.formats"
    # The steps passed over are named, so the app can say why (#1377).
    passed = ["setup.documentation", "setup.storage"]
    assert store.progress(project)["passed_over"] == passed
    assert store.intake(project)["progress"]["passed_over"] == passed
    assert store.summary(project)["progress"]["suggested"] == "setup.formats"
    assert store.intake(project)["progress"]["suggested"] == "setup.formats"
    assert store.snapshot(project).progress(project)["suggested"] == "setup.formats"


def test_each_state_has_the_reason_that_decided_it() -> None:
    events: list[dict[str, Any]] = [
        {"event": progress.ENTRY_CHOSEN, "entry": 1},
        {"event": INVENTORY_ADDED, "at": "2026-11-01T00:00:00+00:00"},
        added("r", "readme"),
        marked("preparation.files", "skipped"),
        marked("governance.embargo", "skipped"),
        {
            "event": progress.INTAKE_ANSWERED,
            "question_id": "intake.sensitive",
            "answer_values": [NO],
        },
        marked("governance.sensitive-data-handle", "open"),
    ]
    reasons = progress.step_reasons(events)
    # The states are step_states', in the same order.
    assert {k: v["state"] for k, v in reasons.items()} == progress.step_states(events)
    assert list(reasons) == list(progress.step_states(events))
    # The log's work outranks a skip and is the reason given.
    assert reasons["preparation.files"]["source"] == "produced"
    assert reasons["preparation.files"]["event"] == INVENTORY_ADDED
    assert "at" in reasons["preparation.files"]
    # A document step names the document that started it.
    assert reasons["preparation.documentation"]["state"] == "started"
    assert reasons["preparation.documentation"]["document_id"] == "r"
    assert reasons["preparation.documentation"]["document_kind"] == "readme"
    assert reasons["governance.embargo"]["source"] == "marked"
    # An answer's skip names its question; a step opened again is open and has none.
    assert reasons["governance.sensitive-data-identify"]["source"] == "intake"
    assert reasons["governance.sensitive-data-identify"]["question_id"] == "intake.sensitive"
    assert "governance.sensitive-data-handle" not in reasons


def test_an_approved_document_is_the_reason_its_step_is_done() -> None:
    reasons = progress.step_reasons([added("m", "metadata_record"), decided("m")])
    assert reasons["preparation.metadata"]["state"] == "done"
    assert reasons["preparation.metadata"]["event"] == DOCUMENT_VERSION_DECIDED
    assert reasons["preparation.metadata"]["document_kind"] == "metadata_record"


def test_the_decisions_are_the_intake_questions_with_their_answers() -> None:
    events: list[dict[str, Any]] = [
        {"event": progress.ENTRY_CHOSEN, "entry": 3},
        {
            "event": progress.INTAKE_ANSWERED,
            "question_id": "intake.repository-mandated",
            "answer_values": [YES],
        },
    ]
    found = {d["question_id"]: d for d in progress.decisions(events)}
    assert "intake.entry" not in found
    mandated = found["intake.repository-mandated"]
    assert mandated["asked"] and mandated["answer_values"] == [YES]
    assert mandated["answer_labels"] == [question("intake.repository-mandated").options[0].label]
    assert mandated["before"] == question("intake.repository-mandated").before
    # Not asked from entry 3, and unanswered.
    assert not found["intake.sensitive"]["asked"]
    assert found["intake.sensitive"]["answer_values"] is None


def test_the_store_refuses_what_is_no_entry_step_or_mark(store: ProjectStore) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    before = store.events(project)
    with pytest.raises(ProjectError):
        store.choose_entry(project, 4, acted_for=TEST_PRINCIPAL, caused_by="test")
    for step_id, mark in (
        ("R5", "done"),
        ("no.such-step", "done"),
        ("governance.embargo", "maybe"),
    ):
        with pytest.raises(ProjectError):
            store.mark_step(project, step_id, mark, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert store.events(project) == before


def test_a_models_entry_point_counts_until_the_researcher_chooses_one(
    store: ProjectStore,
) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    model: progress.EntrySource = progress.ENTRY_BY_MODEL
    assert store.choose_entry(project, 2, acted_for=TEST_PRINCIPAL, caused_by="r", source=model)
    where = store.progress(project)
    assert (where["entry"], where["entry_source"]) == (2, "model")
    assert where["suggested"] is not None and where["suggested"].startswith("governance.")
    # A model may correct its own reading.
    assert store.choose_entry(project, 3, acted_for=TEST_PRINCIPAL, caused_by="r", source=model)
    # The researcher's choice replaces it, and a model's never replaces theirs.
    assert store.choose_entry(project, 2, acted_for=TEST_PRINCIPAL, caused_by="t")
    before = store.events(project)
    assert not store.choose_entry(project, 1, acted_for=TEST_PRINCIPAL, caused_by="r", source=model)
    assert store.events(project) == before
    where = store.progress(project)
    assert (where["entry"], where["entry_source"]) == (2, "researcher")


def test_the_store_refuses_an_entry_point_from_anyone_else(store: ProjectStore) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    with pytest.raises(ProjectError):
        store.choose_entry(
            project,
            2,
            acted_for=TEST_PRINCIPAL,
            caused_by="test",
            source="agent",  # type: ignore[arg-type]
        )
    assert store.progress(project)["entry"] is None


# The intake's answers are the weakest word (docs/specs/projects.md, rule 20).


def chose(entry: int) -> dict[str, Any]:
    return {"event": progress.ENTRY_CHOSEN, "entry": entry}


def answered(question_id: str, *values: str) -> dict[str, Any]:
    return {"event": progress.INTAKE_ANSWERED, "question_id": question_id, "answer_values": values}


def test_only_no_to_an_intake_question_skips_its_steps() -> None:
    no = progress.step_states([chose(2), answered("intake.sensitive", NO)])
    assert set(no) == question("intake.sensitive").skips([NO])
    assert set(no.values()) == {"skipped"}
    for value in (YES, NOT_SURE):
        assert progress.step_states([chose(2), answered("intake.sensitive", value)]) == {}


def test_yes_to_a_mandated_repository_skips_the_recommendation_and_never_marks_a_step_done() -> (
    None
):
    states = progress.step_states([chose(3), answered("intake.repository-mandated", YES)])
    assert states == {"repository.recommend": "skipped"}


def test_an_answer_to_the_dmp_question_skips_the_branch_not_taken_and_marks_nothing_done() -> None:
    for value in (YES, NO, NOT_SURE):
        states = progress.step_states([chose(1), answered("intake.dmp", value)])
        assert states == dict.fromkeys(question("intake.dmp").skips([value]), "skipped")
    assert progress.step_states([chose(1), answered("intake.dmp", YES)])


def test_an_approved_plan_written_after_no_reopens_its_review() -> None:
    review = "setup.dmp-review"
    no = [chose(1), answered("intake.dmp", NO)]
    assert progress.step_states([*no, added("p", "dmp")])[review] == "skipped"
    states = progress.step_states([*no, added("p", "dmp"), decided("p")])
    assert review not in states
    assert states["setup.dmp-create"] == "done"
    kept = [*no, added("p", "dmp"), decided("p"), marked(review, "skipped")]
    assert progress.step_reasons(kept)[review]["source"] == "marked"


def test_the_latest_answer_to_an_intake_question_counts() -> None:
    events = [chose(1), answered("intake.sensitive", NO), answered("intake.sensitive", YES)]
    assert progress.step_states(events) == {}
    skipped = dict.fromkeys(question("intake.sensitive").skips([NO]), "skipped")
    assert progress.step_states([*events, answered("intake.sensitive", NO)]) == skipped


@pytest.mark.parametrize("mark", ["open", "done"])
def test_a_researchers_mark_overrides_an_intake_skip(mark: str) -> None:
    step = "governance.sensitive-data-identify"
    events = [chose(1), answered("intake.sensitive", NO), marked(step, mark)]
    assert progress.step_states(events).get(step, "open") == mark


def test_work_the_log_shows_overrides_an_intake_skip() -> None:
    events = [chose(3), answered("intake.repository-mandated", NO), {"event": REPOSITORY_CHOSEN}]
    states = progress.step_states([*events, marked("repository.mandated", "open")])
    assert "repository.mandated" not in states
    assert progress.step_states(events)["repository.recommend"] == "done"


def test_an_intake_answer_counts_only_from_an_entry_point_that_asks_it() -> None:
    events = [chose(2), answered("intake.sensitive", NO)]
    assert "governance.sensitive-data-handle" in progress.step_states(events)
    assert "governance.sensitive-data-handle" not in progress.step_states([*events, chose(3)])

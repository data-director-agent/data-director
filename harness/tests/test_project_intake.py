"""The project intake's answers, recorded in the project log, and where the intake stands
(docs/specs/projects.md, rule 20; `dd_harness.intake`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dd_harness import intake, progress
from dd_harness.projects import ProjectError, ProjectStore, UnknownProjectError
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.intake import ENTRY, INTAKE, NO, NOT_SURE, YES, question
from dd_sdk.process_flow import ENTRIES


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project(store: ProjectStore) -> str:
    return store.create(acted_for=TEST_PRINCIPAL, caused_by="test")


def answer(store: ProjectStore, project: str, question_id: str, *values: str) -> None:
    store.answer_intake(project, question_id, values, acted_for=TEST_PRINCIPAL, caused_by="test")


def asked(store: ProjectStore, project: str) -> str | None:
    q = intake.next_question(store.events(project))
    return q.id if q is not None else None


def test_a_new_project_is_asked_the_entry_question_first(store: ProjectStore, project: str) -> None:
    assert asked(store, project) == ENTRY
    assert store.summary(project)["intake"] == intake.PENDING


@pytest.mark.parametrize("entry", [e.number for e in ENTRIES])
def test_the_intake_asks_each_question_its_entry_point_reaches_then_completes(
    store: ProjectStore, project: str, entry: int
) -> None:
    answer(store, project, ENTRY, str(entry))
    seen = [ENTRY]
    while (next_id := asked(store, project)) is not None:
        seen.append(next_id)
        answer(store, project, next_id, NOT_SURE)
    assert seen == [q.id for q in INTAKE if q.asked_at(entry)]
    assert store.summary(project)["intake"] == intake.COMPLETE


def test_the_entry_answer_is_the_researchers_entry_point(store: ProjectStore, project: str) -> None:
    answer(store, project, ENTRY, "2")
    last = store.events(project)[-1]
    assert last["event"] == progress.ENTRY_CHOSEN
    assert progress.entry_and_source(store.events(project)) == (2, progress.ENTRY_BY_RESEARCHER)


def test_any_entry_point_recorded_answers_the_entry_question(
    store: ProjectStore, project: str
) -> None:
    store.choose_entry(
        project, 3, acted_for=TEST_PRINCIPAL, caused_by="run", source=progress.ENTRY_BY_MODEL
    )
    assert asked(store, project) == "intake.repository-mandated"


def test_another_answer_is_an_intake_answered_event_and_skips_on_no(
    store: ProjectStore, project: str
) -> None:
    answer(store, project, ENTRY, "1")
    answer(store, project, "intake.dmp", NO)
    last = store.events(project)[-1]
    assert last["event"] == progress.INTAKE_ANSWERED
    assert (last["question_id"], last["answer_values"]) == ("intake.dmp", [NO])
    steps = store.progress(project)["steps"]
    assert {s for s, state in steps.items() if state == "skipped"} == question("intake.dmp").skips(
        [NO]
    )
    # Answering again replaces the answer.
    answer(store, project, "intake.dmp", YES)
    assert store.progress(project)["steps"] == {}


def test_a_dismissal_stands_until_an_answer_is_recorded_after_it(
    store: ProjectStore, project: str
) -> None:
    store.dismiss_intake(project, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert store.events(project)[-1]["event"] == progress.INTAKE_DISMISSED
    assert asked(store, project) is None
    assert store.summary(project)["intake"] == intake.DISMISSED
    answer(store, project, ENTRY, "1")
    assert asked(store, project) == "intake.dmp"
    assert store.summary(project)["intake"] == intake.PENDING


@pytest.mark.parametrize(
    ("question_id", "values"),
    [
        ("intake.funder", (YES,)),  # no such question
        ("intake.dmp", ()),  # nothing chosen
        ("intake.dmp", (YES, NO)),  # one answer only
        ("intake.dmp", ("perhaps",)),  # not an option
        (ENTRY, ("4",)),  # no such entry point
        ("intake.sensitive", (NO,)),  # not asked from entry 3
    ],
)
def test_an_answer_that_fails_its_check_records_nothing(
    store: ProjectStore, project: str, question_id: str, values: tuple[str, ...]
) -> None:
    answer(store, project, ENTRY, "3")
    before = store.events(project)
    with pytest.raises(ProjectError):
        answer(store, project, question_id, *values)
    assert store.events(project) == before


def test_an_unknown_project_is_refused(store: ProjectStore) -> None:
    missing = "01900000-0000-7000-8000-000000000000"
    with pytest.raises(UnknownProjectError):
        answer(store, missing, ENTRY, "1")
    with pytest.raises(UnknownProjectError):
        store.dismiss_intake(missing, acted_for=TEST_PRINCIPAL, caused_by="test")


def test_the_intake_read_lists_the_questions_asked_from_the_entry_with_their_answers(
    store: ProjectStore, project: str
) -> None:
    before = store.intake(project)
    assert before["state"] == intake.PENDING
    assert before["next"] == ENTRY
    # With no entry point, only the entry question is asked.
    assert [q["question_id"] for q in before["questions"]] == [ENTRY]
    assert before["questions"][0]["answer_values"] is None
    assert before["questions"][0]["question"]["question_kind"] == "choice"

    third = ENTRIES[-1].number
    answer(store, project, ENTRY, str(third))
    answer(store, project, "intake.repository-mandated", NO)
    read = store.intake(project)
    assert [q["question_id"] for q in read["questions"]] == [
        q.id for q in INTAKE if q.asked_at(third)
    ]
    answers = {q["question_id"]: q["answer_values"] for q in read["questions"]}
    assert answers[ENTRY] == [str(third)]
    assert answers["intake.repository-mandated"] == [NO]
    assert read["progress"]["entry"] == third


def test_a_complete_intake_reads_with_the_step_suggested_and_no_next_question(
    store: ProjectStore, project: str
) -> None:
    answer(store, project, ENTRY, str(ENTRIES[0].number))
    for q in INTAKE[1:]:
        if q.asked_at(ENTRIES[0].number):
            answer(store, project, q.id, NOT_SURE)
    read = store.intake(project)
    assert read["state"] == intake.COMPLETE
    assert read["next"] is None
    assert read["progress"]["suggested"] is not None


def test_a_dismissed_intake_reads_as_dismissed_with_no_next_question(
    store: ProjectStore, project: str
) -> None:
    store.dismiss_intake(project, acted_for=TEST_PRINCIPAL, caused_by="test")
    read = store.intake(project)
    assert read["state"] == intake.DISMISSED
    assert read["next"] is None

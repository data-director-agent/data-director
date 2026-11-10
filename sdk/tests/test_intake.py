"""The project intake's questions, as Blueprint data (docs/specs/orchestration.md, invariant 20)."""

from __future__ import annotations

import pytest

from dd_sdk.contract.models import ChoiceQuestion
from dd_sdk.intake import ENTRY, INTAKE, NO, NOT_SURE, YES, IntakeQuestion, question
from dd_sdk.process_flow import ENTRIES, OUT_OF_SCOPE, STEPS

EXPECTED_SKIPS = {
    "intake.dmp": {"governance.dmp"},
    "intake.sensitive": {"governance.sensitive-data-identify", "governance.sensitive-data-handle"},
    "intake.repository-mandated": {"repository.mandated"},
}


def test_the_intake_asks_the_entry_question_first_then_the_decision_points() -> None:
    ids = [q.id for q in INTAKE]
    assert ids[0] == ENTRY
    assert set(ids[1:]) == set(EXPECTED_SKIPS)
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize("q", INTAKE, ids=lambda q: q.id)
def test_each_question_converts_to_a_core_choice_question(q: IntakeQuestion) -> None:
    asked = q.choice_question()
    assert ChoiceQuestion.model_validate(asked.model_dump()) == asked
    assert asked.question_prompt == q.prompt
    assert [o.option_value for o in asked.question_options] == [o.value for o in q.options]
    assert not asked.question_multiple
    assert not asked.question_other


def test_every_skip_names_a_known_step_that_is_in_scope() -> None:
    skipped = {s for q in INTAKE for o in q.options for s in o.skips}
    assert skipped <= STEPS
    assert not skipped & OUT_OF_SCOPE


def test_the_entry_questions_values_are_exactly_the_entry_numbers() -> None:
    entry = question(ENTRY)
    assert {o.value for o in entry.options} == {str(e.number) for e in ENTRIES}
    assert not entry.skips(o.value for o in entry.options)


@pytest.mark.parametrize("question_id", sorted(EXPECTED_SKIPS))
def test_only_no_skips_steps_and_not_sure_is_always_offered(question_id: str) -> None:
    q = question(question_id)
    assert {o.value for o in q.options} == {YES, NO, NOT_SURE}
    assert q.skips([NO]) == EXPECTED_SKIPS[question_id]
    assert not q.skips([YES])
    assert not q.skips([NOT_SURE])


def test_each_question_is_asked_only_from_the_entry_points_that_reach_its_step() -> None:
    numbers = {e.number for e in ENTRIES}
    for q in INTAKE:
        assert set(q.asked_from) <= numbers
    asked = {e.number: [q.id for q in INTAKE if q.asked_at(e.number)] for e in ENTRIES}
    assert asked[1] == asked[2] == [q.id for q in INTAKE]
    assert asked[3] == [ENTRY, "intake.repository-mandated"]
    # Before the entry point is known, only the entry question is asked.
    assert [q.id for q in INTAKE if q.asked_at(None)] == [ENTRY]


def test_an_unknown_question_is_refused() -> None:
    with pytest.raises(KeyError):
        question("intake.funder")

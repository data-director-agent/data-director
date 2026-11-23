"""Step and intake question ids are stored in project logs, so none is ever deleted, only retired
(docs/specs/projects.md). `released_ids.toml` lists every id a release has had; these tests hold
the flow and the intake to it, so that a project log written by any earlier release still reads."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from dd_sdk.intake import INTAKE, RETIRED_QUESTIONS, current_question
from dd_sdk.process_flow import RETIRED_STEPS, STEPS, current_step

RELEASED = tomllib.loads((Path(__file__).parent / "released_ids.toml").read_text())
RELEASED_STEPS = frozenset(RELEASED["steps"])
RELEASED_QUESTIONS = frozenset(RELEASED["intake_questions"])
QUESTIONS = frozenset(q.id for q in INTAKE)


def test_every_step_is_in_the_ledger() -> None:
    missing = sorted(STEPS - RELEASED_STEPS)
    assert not missing, f"add {missing} to sdk/tests/released_ids.toml"


def test_no_released_step_is_deleted() -> None:
    gone = sorted(RELEASED_STEPS - STEPS - RETIRED_STEPS.keys())
    assert not gone, (
        f"project logs may name {gone}: retire them in dd_sdk.flow_phases.RETIRED_STEPS, with "
        "the step that replaces each or None, rather than deleting them"
    )


def test_every_question_is_in_the_ledger() -> None:
    missing = sorted(QUESTIONS - RELEASED_QUESTIONS)
    assert not missing, f"add {missing} to sdk/tests/released_ids.toml"


def test_no_released_question_is_deleted() -> None:
    gone = sorted(RELEASED_QUESTIONS - QUESTIONS - RETIRED_QUESTIONS.keys())
    assert not gone, (
        f"project logs may name {gone}: retire them in dd_sdk.intake.RETIRED_QUESTIONS, with "
        "the question that replaces each or None, rather than deleting them"
    )


@pytest.mark.parametrize(
    ("retired", "live", "released"),
    [
        (RETIRED_STEPS, STEPS, RELEASED_STEPS),
        (RETIRED_QUESTIONS, QUESTIONS, RELEASED_QUESTIONS),
    ],
    ids=["steps", "questions"],
)
def test_a_retired_id_is_released_not_live_and_replaced_by_a_live_one(
    retired: dict[str, str | None], live: frozenset[str], released: frozenset[str]
) -> None:
    assert not retired.keys() & live
    assert retired.keys() <= released
    assert {s for s in retired.values() if s is not None} <= live


def test_a_stored_step_id_resolves_to_a_live_step_or_none() -> None:
    for step_id in RELEASED_STEPS | {"later.step"}:
        resolved = current_step(step_id)
        assert resolved is None or resolved in STEPS
    assert all(current_step(s) == s for s in STEPS)
    assert current_step("later.step") is None


def test_a_stored_question_id_resolves_to_a_live_question_or_none() -> None:
    for question_id in RELEASED_QUESTIONS | {"intake.later"}:
        resolved = current_question(question_id)
        assert resolved is None or resolved in QUESTIONS
    assert all(current_question(q) == q for q in QUESTIONS)
    assert current_question("intake.later") is None

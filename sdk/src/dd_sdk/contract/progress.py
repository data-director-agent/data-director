"""Pydantic mirrors of where a project is in the Blueprint's process flow, as the conductor gives
it to an orchestrator on a `Message` (schema/data_director.yaml, docs/specs/orchestration.md):
how far each step has gone, and the researcher's answers to the intake's setup questions.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from dd_sdk.contract.base import Frozen


class StepState(StrEnum):
    STARTED = "started"
    DONE = "done"
    SKIPPED = "skipped"


class StepProgress(Frozen):
    """How far one process-flow step has gone, as the project log shows it; a step left out is
    open (docs/specs/orchestration.md)."""

    step_id: str = Field(pattern=r"^[a-z]+\.[a-z-]+$")
    step_state: StepState


class IntakeAnswer(Frozen):
    """The researcher's current answer to one intake question beside the entry question
    (`dd_sdk.intake`), with the labels of the options chosen (docs/specs/orchestration.md,
    invariant 20)."""

    intake_question_id: str = Field(pattern=r"^intake\.[a-z-]+$")
    intake_question_prompt: str
    intake_answer_labels: list[str] = Field(min_length=1)

"""The graph's state.

A `TypedDict` rather than a Pydantic model, deliberately. LangGraph accepts a `BaseModel` as a
state schema, but the trade is bad here: a validation error does not name the node that caused
it, graph output is not a model instance, and recursive validation runs on every super-step. So
the state is a plain mapping holding *already-validated* Pydantic objects, and each node
validates its own payload as it builds it. That puts the validation error next to the code that
caused it, which is the only place it is useful.

Each key has exactly one writer, except the two reducer lists that every node appends to.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from standards_advisor.models.candidates import (
    CandidateSet,
    CheckOutcome,
    Explanation,
    RankedCandidateSet,
)
from standards_advisor.models.common import StageFailure, StageReport
from standards_advisor.models.elicitation import ElicitedContext
from standards_advisor.models.inputs import DatasetInput
from standards_advisor.models.profile import DatasetProfile
from standards_advisor.models.recommendations import RecommendationsDocument


class PipelineState(TypedDict, total=False):
    """§5's stages, as state.

    | Key | Written by |
    |---|---|
    | `run_id`, `inputs` | seeded at `invoke()` |
    | `answers` | `elicit` |
    | `profile` | `profile` |
    | `candidates` | `retrieve` |
    | `ranked` | `rank` |
    | `explanations` | `explain` |
    | `checked` | `check` |
    | `document` | `assemble` |
    | `stage_reports`, `failures` | any node, by appending |
    """

    run_id: str
    inputs: DatasetInput

    answers: ElicitedContext | None
    """What the researcher was asked and answered (§8). `None` outside pre-collection.

    This is the one piece of state that has to survive a *process* boundary rather than just a
    super-step: the graph pauses here for a human, and the answers are read back by a later
    invocation. LangGraph serialises state models with a module-path marker, so moving or
    renaming `ElicitedContext` breaks resuming an older checkpoint — see
    `test_pydantic_objects_survive_a_checkpoint_round_trip`."""

    profile: DatasetProfile | None
    candidates: CandidateSet | None
    ranked: RankedCandidateSet | None
    explanations: list[Explanation] | None
    checked: CheckOutcome | None
    document: RecommendationsDocument | None

    stage_reports: Annotated[list[StageReport], operator.add]
    failures: Annotated[list[StageFailure], operator.add]
    """Content-level problems, recorded as data. See `errors` for why these are not raised."""


def initial_state(run_id: str, inputs: DatasetInput) -> PipelineState:
    return PipelineState(
        run_id=run_id,
        inputs=inputs,
        answers=None,
        profile=None,
        candidates=None,
        ranked=None,
        explanations=None,
        checked=None,
        document=None,
        stage_reports=[],
        failures=[],
    )

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
from standards_advisor.models.inputs import DatasetInput
from standards_advisor.models.profile import DatasetProfile
from standards_advisor.models.recommendations import RecommendationsDocument


class PipelineState(TypedDict, total=False):
    """§5's six stages, as state.

    | Key | Written by |
    |---|---|
    | `run_id`, `inputs` | seeded at `invoke()` |
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
        profile=None,
        candidates=None,
        ranked=None,
        explanations=None,
        checked=None,
        document=None,
        stage_reports=[],
        failures=[],
    )

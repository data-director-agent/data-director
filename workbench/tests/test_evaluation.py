"""The evaluation solver, scorers and run comparison, over a scripted agent (ADR-0013).

These test the machinery. They substantiate no requirement: an evaluation result is not a
conformance claim, so nothing here carries a requirement marker.
"""

from __future__ import annotations

import gc
import json
import math
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from inspect_ai import Task
from inspect_ai import eval as inspect_eval
from inspect_ai.dataset import Sample
from inspect_ai.scorer import NOANSWER, SampleScore, Score

from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import (
    GroundingMode,
    InvocationRequest,
    MetadataRecord,
    Outcome,
    OutcomeStatus,
    QualityReview,
    ReasonCode,
)
from workbench.evaluation import (
    ANSWERED_NEEDLESSLY,
    FAILED,
    STOPPED_NEEDLESSLY,
    Scores,
    differences,
    grounding_passed,
    invoke_agent,
    mean_applicable,
    outcome_matches,
    stopped_correctly,
)
from workbench.testing import (
    TEST_PRINCIPAL,
    ScriptedAgent,
    make_conductor,
    record,
    review_of_input,
)

# Inspect AI leaves its sample-event stream unclosed (inspect_ai/hooks/_hooks.py, the sample
# event emitter); with warnings as errors, its deallocator warning fails whichever test is
# running when it is collected. The filter is scoped to this module, so a stream leaked by the
# workbench still fails elsewhere, and `collect_inspect_streams` makes sure the collection
# happens here rather than in a later module.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Unclosed <MemoryObjectReceiveStream:ResourceWarning"
)


@pytest.fixture(autouse=True)
def collect_inspect_streams() -> Iterator[None]:
    yield
    gc.collect()


def behaviour(request: InvocationRequest, ctx: RunContext) -> AgentResult:
    """What the scripted agent does is named by the record's title."""
    assert isinstance(request.input, MetadataRecord)
    title = request.input.title
    if title == "abstain":
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.ABSTAINED,
                reason_code=ReasonCode.INSUFFICIENT_INPUT,
                statement="Nothing to go on.",
            )
        )
    if title == "ungrounded":
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Reviewed."),
            payload=QualityReview(score=1.0, grounded_on=[]),
        )
    return review_of_input(request, ctx)


def case(case_id: str, title: str, status: str, **expect: Any) -> Sample:
    doc = record().model_copy(update={"title": title}).model_dump(mode="json", exclude_none=True)
    return Sample(
        id=case_id,
        input=json.dumps(doc),
        target=status,
        metadata={"expect": {"status": status, **expect}},
    )


CASES = [
    case("answers", "answer", "succeeded"),
    case("stops", "abstain", "abstained", reason_code="insufficient_input"),
    case("wrong-reason", "abstain", "abstained", reason_code="registry_unavailable"),
    case("stops-needlessly", "abstain", "succeeded"),
    case("answers-needlessly", "answer", "abstained"),
    case("ungrounded", "ungrounded", "succeeded"),
]


def run(tmp_path: Path) -> Any:
    agent = ScriptedAgent(GroundingMode.INPUT_ONLY, behaviour)
    built: list[Any] = []

    def conductor_for(_case: dict[str, Any]) -> Any:
        if not built:  # built on the solver's worker thread, as `invoke_agent` requires
            built.append(make_conductor(tmp_path / "runs", agent))
        return built[0]

    task = Task(
        dataset=CASES,
        solver=invoke_agent(conductor_for, agent.spec.agent_id, TEST_PRINCIPAL),
        scorer=[outcome_matches(), stopped_correctly(), grounding_passed()],
    )
    [log] = inspect_eval(task, model="none", log_dir=str(tmp_path / "logs"), display="none")
    assert log.status == "success", log.error
    return log


def test_each_case_is_scored_on_outcome_stopping_and_grounding(tmp_path):
    log = run(tmp_path)
    got = {
        str(s.id): {name: score.value for name, score in (s.scores or {}).items()}
        for s in log.samples
    }
    assert got == {
        "answers": {"outcome_matches": "C", "stopped_correctly": "C", "grounding_passed": "C"},
        "stops": {"outcome_matches": "C", "stopped_correctly": "C", "grounding_passed": "C"},
        "wrong-reason": {"outcome_matches": "I", "stopped_correctly": "C", "grounding_passed": "C"},
        "stops-needlessly": {
            "outcome_matches": "I",
            "stopped_correctly": "I",
            "grounding_passed": "C",
        },
        "answers-needlessly": {
            "outcome_matches": "I",
            "stopped_correctly": "I",
            "grounding_passed": "C",
        },
        # The linter withholds the ungrounded payload, so the run failed.
        "ungrounded": {"outcome_matches": "I", "stopped_correctly": "I", "grounding_passed": "I"},
    }


def test_the_sample_keeps_the_envelope_and_the_linter_report(tmp_path):
    log = run(tmp_path)
    ungrounded = next(s for s in log.samples if s.id == "ungrounded")
    assert ungrounded.metadata["envelope"]["outcome"]["status"] == "failed"
    assert ungrounded.metadata["grounding"]["passed"] is False
    assert ungrounded.metadata["grounding"]["violations"]
    assert ungrounded.output.completion.startswith("Output withheld")


def test_stopping_errors_are_counted_apart_and_a_failed_run_is_neither(tmp_path):
    log = run(tmp_path)
    kinds = {str(s.id): s.scores["stopped_correctly"].answer for s in log.samples}
    assert kinds["stops-needlessly"] == STOPPED_NEEDLESSLY
    assert kinds["answers-needlessly"] == ANSWERED_NEEDLESSLY
    assert kinds["ungrounded"] == FAILED
    [scores] = [s for s in log.results.scores if s.name == "stopped_correctly"]
    # Five cases did not fail; one of them stopped needlessly and one answered needlessly.
    assert scores.metrics["stopped_needlessly"].value == 1 / 5
    assert scores.metrics["answered_needlessly"].value == 1 / 5


def test_a_case_a_scorer_does_not_apply_to_is_left_out_of_the_mean():
    scores = [
        SampleScore(score=Score(value=1.0), sample_id="a"),
        SampleScore(score=Score(value=0.5), sample_id="b"),
        SampleScore(score=Score(value=NOANSWER), sample_id="c"),
    ]
    mean = cast(Callable[[list[SampleScore]], float], mean_applicable())
    assert mean(scores) == 0.75
    assert math.isnan(mean([SampleScore(score=Score(value=NOANSWER))]))


def test_a_lower_score_or_a_missing_case_is_a_regression():
    old: Scores = {"a": {"recall": 1.0, "wrong": 1.0}, "b": {"recall": None}, "c": {"recall": 0.5}}
    new: Scores = {"a": {"recall": 0.5, "wrong": 1.0}, "b": {"recall": 0.0}, "d": {"recall": 1.0}}
    regressions, changes = differences(old, new)
    assert regressions == ["a recall: 1 -> 0.5", "c: missing from the new run"]
    # A score that starts to apply is not a regression, whatever its value.
    assert changes == ["b recall: n/a -> 0", "d: new case"]


def test_a_rise_is_a_change_and_a_score_that_stops_applying_is_a_regression():
    regressions, changes = differences({"a": {"x": 0.5, "y": 1.0}}, {"a": {"x": 1.0, "y": None}})
    assert regressions == ["a y: 1 -> n/a"]
    assert changes == ["a x: 0.5 -> 1"]

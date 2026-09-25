"""R3's own scorers: whether it recommended what the case expects, and nothing it should not.

Recall and wrong recommendations are separate scores, never one blended figure: a missed
standard and a confidently wrong one are different failures, and the second is the worse.
"""

from __future__ import annotations

from typing import Any

from inspect_ai.scorer import CORRECT, INCORRECT, NOANSWER, Score, Scorer, Target, accuracy, scorer
from inspect_ai.solver import TaskState

from workbench.evaluation import envelope_of, expectation_of, mean_applicable


def recommended(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = (envelope.get("payload") or {}).get("items", [])
    return items


@scorer(metrics=[mean_applicable()])
def expected_recall() -> Scorer:
    """The share of the case's `include` ids and `kinds_present` kinds that R3 recommended.
    Does not apply to a case that expects neither."""

    async def score(state: TaskState, target: Target) -> Score:
        expect = expectation_of(state)
        items = recommended(envelope_of(state))
        ids = {i["resource"]["fairsharing_id"] for i in items}
        kinds = {i["kind"] for i in items}
        wanted = [("id", x) for x in expect.get("include", [])] + [
            ("kind", k) for k in expect.get("kinds_present", [])
        ]
        if not wanted:
            return Score(value=NOANSWER, explanation="the case expects no recommendation")
        missing = [f"{what} {x}" for what, x in wanted if x not in (ids if what == "id" else kinds)]
        found = len(wanted) - len(missing)
        return Score(
            value=found / len(wanted),
            answer=f"{found}/{len(wanted)}",
            explanation="missing: " + ", ".join(missing) if missing else "all found",
            metadata={"missing": missing},
        )

    return score


@scorer(metrics=[accuracy()])
def no_wrong_recommendations() -> Scorer:
    """R3 recommended nothing the case marks wrong: no `exclude` id, no `kinds_absent` kind,
    and no deprecated record. An abstention recommends nothing and so passes."""

    async def score(state: TaskState, target: Target) -> Score:
        expect = expectation_of(state)
        exclude = set(expect.get("exclude", []))
        kinds_absent = set(expect.get("kinds_absent", []))
        wrong: list[str] = []
        for item in recommended(envelope_of(state)):
            resource = item["resource"]
            rid = resource["fairsharing_id"]
            if rid in exclude:
                wrong.append(f"{rid} ({resource.get('name')}) is labelled wrong for this case")
            if item["kind"] in kinds_absent:
                wrong.append(f"{rid} is a {item['kind']} recommendation, which this case rules out")
            if resource.get("status") == "deprecated":
                wrong.append(f"{rid} is deprecated")
        wrong = sorted(set(wrong))
        return Score(
            value=INCORRECT if wrong else CORRECT,
            answer=str(len(wrong)),
            explanation="; ".join(wrong) or "none",
            metadata={"wrong": wrong},
        )

    return score

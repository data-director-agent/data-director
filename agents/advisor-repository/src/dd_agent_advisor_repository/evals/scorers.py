"""The repository advisor's own scorers: whether the repositories a data management plan names
reach the researcher as the plan's, and whether a shortlist is still made beside them.

Each is a separate score, never blended with another. A scorer that does not apply to a case
returns NOANSWER.
"""

from __future__ import annotations

from typing import Any

from inspect_ai.scorer import CORRECT, INCORRECT, NOANSWER, Score, Scorer, Target, accuracy, scorer
from inspect_ai.solver import TaskState

from workbench.evaluation import envelope_of, expectation_of, mean_applicable

IN_PLAN = "in_plan"
RECOMMENDED = "recommended"


def payload(state: TaskState) -> dict[str, Any]:
    """The run's payload, or an empty one where it stopped."""
    found: dict[str, Any] = envelope_of(state).get("payload") or {}
    return found


def shown_in_plan(options: dict[str, Any]) -> set[str]:
    """The names of the repositories re3data does not list that the payload shows as the plan's
    (`unlisted`, basis `in_plan`). The cases name only such repositories; one re3data lists is a
    candidate, named only by its record (docs/specs/grounding.md)."""
    return {
        str(entry.get("name", "")).casefold()
        for entry in options.get("unlisted", [])
        if entry.get("basis") == IN_PLAN
    }


@scorer(metrics=[mean_applicable()])
def plan_repositories_shown() -> Scorer:
    """The share of the repositories the plan names that the payload shows as the plan's. Does
    not apply to a case whose plan names none or is not confirmed."""

    async def score(state: TaskState, target: Target) -> Score:
        expected: list[str] = expectation_of(state).get("in_plan", [])
        if not expected:
            return Score(value=NOANSWER, explanation="no confirmed plan names a repository")
        shown = shown_in_plan(payload(state))
        missing = [name for name in expected if name.casefold() not in shown]
        found = len(expected) - len(missing)
        return Score(
            value=found / len(expected),
            answer=f"{found}/{len(expected)}",
            explanation="not shown: " + ", ".join(missing) if missing else "all shown",
            metadata={"missing": missing},
        )

    return score


@scorer(metrics=[accuracy()])
def shortlist_kept() -> Scorer:
    """Where the case expects a shortlist, at least one repository is recommended: what the plan
    names adds to the shortlist and removes nothing."""

    async def score(state: TaskState, target: Target) -> Score:
        if not expectation_of(state).get("shortlist"):
            return Score(value=NOANSWER, explanation="no shortlist is expected")
        recommended = [
            c for c in payload(state).get("candidates", []) if c.get("basis") == RECOMMENDED
        ]
        return Score(
            value=CORRECT if recommended else INCORRECT,
            answer=str(len(recommended)),
            explanation=f"{len(recommended)} recommended",
        )

    return score

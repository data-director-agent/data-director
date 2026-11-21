"""The repository advisor's own scorers: whether the repositories a data management plan names
reach the researcher as the plan's, whether the researcher's own institution's repository is
offered, and only to its researchers, and whether a shortlist is still made beside them.

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


def cited(options: dict[str, Any], basis: str | None = None) -> set[str]:
    """The registry identifiers of the candidates, of `basis` where given: each candidate is
    named by its first grounding, its registry's record (docs/specs/grounding.md)."""
    return {
        str(c["grounded_on"][0]["source_id"])
        for c in options.get("candidates", [])
        if c.get("grounded_on") and (basis is None or c.get("basis") == basis)
    }


@scorer(metrics=[mean_applicable()])
def plan_repositories_shown() -> Scorer:
    """The share of the repositories the plan names, by registry identifier, that the payload
    offers as the plan's, so that the researcher can choose them. Does not apply to a case whose
    plan names none or is not confirmed."""

    async def score(state: TaskState, target: Target) -> Score:
        expected: list[str] = expectation_of(state).get("in_plan", [])
        if not expected:
            return Score(value=NOANSWER, explanation="no confirmed plan names a repository")
        shown = cited(payload(state), IN_PLAN)
        missing = [rid for rid in expected if rid not in shown]
        found = len(expected) - len(missing)
        return Score(
            value=found / len(expected),
            answer=f"{found}/{len(expected)}",
            explanation="not shown: " + ", ".join(missing) if missing else "all shown",
            metadata={"missing": missing},
        )

    return score


@scorer(metrics=[mean_applicable()])
def institution_repository_offered() -> Scorer:
    """The share of the case's expectations about institutions' own repositories that hold: each
    of `institutional` is offered, and none of `not_offered` is. Does not apply to a case that
    names neither."""

    async def score(state: TaskState, target: Target) -> Score:
        expect = expectation_of(state)
        offered: list[str] = expect.get("institutional", [])
        withheld: list[str] = expect.get("not_offered", [])
        if not (offered or withheld):
            return Score(value=NOANSWER, explanation="no institution's repository is expected")
        found = cited(payload(state))
        wrong = [rid for rid in offered if rid not in found] + [r for r in withheld if r in found]
        total = len(offered) + len(withheld)
        return Score(
            value=(total - len(wrong)) / total,
            answer=f"{total - len(wrong)}/{total}",
            explanation="wrong: " + ", ".join(wrong) if wrong else "as expected",
            metadata={"wrong": wrong},
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

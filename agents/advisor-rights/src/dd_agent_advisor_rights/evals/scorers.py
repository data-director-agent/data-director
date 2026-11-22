"""The Rights and Licensing Adviser's own scorers: the access levels it puts first, and the
questions it must ask. Which licences it lists, and which it must not, are scored by the
workbench's `ids_recalled` and `none_listed` over `licences`.

Questions are matched to the adviser's own question constants, not to wording written here, so a
reworded question is still recognised.
"""

from __future__ import annotations

from typing import Any

from inspect_ai.scorer import NOANSWER, Score, Scorer, Target, scorer
from inspect_ai.solver import TaskState

from dd_agent_advisor_rights import agent
from workbench.evaluation import envelope_of, expectation_of, mean_applicable

# A kind of question a case can require, and the adviser's question of that kind.
QUESTIONS = {
    "reuse": agent.REUSE_QUESTION,
    "sensitive": agent.SENSITIVE_QUESTION,
    "unknown_sensitive": agent.UNKNOWN_SENSITIVE_QUESTION,
    "third_party": agent.THIRD_PARTY_QUESTION,
    "mandated_reuse": agent.MANDATED_REUSE_QUESTION,
}


def _payload(state: TaskState) -> dict[str, Any]:
    payload: dict[str, Any] = envelope_of(state).get("payload") or {}
    return payload


@scorer(metrics=[mean_applicable()])
def access_first() -> Scorer:
    """Whether the access levels the case names in `access_first` lead the list, in that order:
    for sensitive data, restricted and closed before open. Does not apply to a case that names
    none."""

    async def score(state: TaskState, target: Target) -> Score:
        wanted = list(expectation_of(state).get("access_first", []))
        if not wanted:
            return Score(value=NOANSWER, explanation="the case names no leading access level")
        got = [a["level"] for a in _payload(state).get("access_levels", [])][: len(wanted)]
        return Score(
            value=1.0 if got == wanted else 0.0,
            answer=", ".join(got) or "none",
            explanation=f"expected {', '.join(wanted)} first",
        )

    return score


@scorer(metrics=[mean_applicable()])
def questions_asked() -> Scorer:
    """The share of the kinds of question the case names in `questions` that the adviser asked,
    with each one missed in the score's metadata. Does not apply to a case that names none."""

    async def score(state: TaskState, target: Target) -> Score:
        wanted = list(expectation_of(state).get("questions", []))
        if not wanted:
            return Score(value=NOANSWER, explanation="the case names no question it must ask")
        asked = {" ".join(q["text"].split()) for q in _payload(state).get("questions", [])}
        missing = [k for k in wanted if " ".join(QUESTIONS[k].split()) not in asked]
        found = len(wanted) - len(missing)
        return Score(
            value=found / len(wanted),
            answer=f"{found}/{len(wanted)}",
            explanation="missing: " + ", ".join(missing) if missing else "all asked",
            metadata={"missing": missing},
        )

    return score

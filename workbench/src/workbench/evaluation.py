"""Evaluation on Inspect AI (ADR-0013): an agent run over a fixed case set, each case scored.

This module holds what is common to every agent's evaluation:

- a solver that sends each case through the conductor, so the policy gate, the input check and
  the grounding linter run exactly as they do for any other invocation;
- scorers for the outcome, for whether the agent stopped when it should have, and for the
  linter's verdict;
- metrics that leave a case out when a scorer does not apply to it, rather than counting it as
  zero;
- the comparison of two runs' per-case scores, which `workbench/scripts/eval_compare.py` and
  each agent's baseline test apply.

A case is an Inspect `Sample`: `input` is the input document as JSON, and `metadata["expect"]`
is what the case expects. What an agent should recommend is agent-specific and is scored beside
that agent (for the standards advisor, `dd_agent_standards.evals`).

Needs the `eval` extra (`inspect-ai`). Like the rest of `src/`, it imports no agent.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from inspect_ai.log import EvalLog
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    NOANSWER,
    Metric,
    SampleScore,
    Score,
    Scorer,
    Target,
    accuracy,
    metric,
    scorer,
    value_to_float,
)
from inspect_ai.solver import Generate, Solver, TaskState, solver

from dd_harness.conductor import Conductor
from dd_sdk.contract.models import InvocationRequest, OpenInput, Principal

# The statuses in which an agent declined to answer. The source delivery plan counts them as
# success states, scored apart from `failed`: stopping correctly is a right answer.
STOP_STATUSES = frozenset({"abstained", "referred", "suspended"})

# How `stopped_correctly` classifies a case; the two error kinds are counted separately.
STOPPED_AS_EXPECTED = "stopped-as-expected"
ANSWERED_AS_EXPECTED = "answered-as-expected"
STOPPED_NEEDLESSLY = "stopped-when-it-should-have-answered"
ANSWERED_NEEDLESSLY = "answered-when-it-should-have-stopped"
FAILED = "failed"

ConductorFor = Callable[[dict[str, Any]], Conductor]
"""Returns the conductor for a case, given the case's metadata. Called off the event loop (see
`invoke_agent`)."""


# --- Metrics ----------------------------------------------------------------------------------


def _applicable(scores: list[SampleScore]) -> list[float]:
    to_float = value_to_float()
    return [to_float(s.score.value) for s in scores if s.score.value != NOANSWER]


@metric
def mean_applicable() -> Metric:
    """The mean over the cases a scorer applies to. Inspect's own `mean` and `accuracy` count
    NOANSWER as 0; a case with nothing to score is not a case scored zero."""

    def compute(scores: list[SampleScore]) -> float:
        values = _applicable(scores)
        return sum(values) / len(values) if values else float("nan")

    return compute


def _share(kind: str) -> Metric:
    def compute(scores: list[SampleScore]) -> float:
        judged = [s for s in scores if (s.score.metadata or {}).get("stop") != FAILED]
        if not judged:
            return float("nan")
        return sum(1 for s in judged if (s.score.metadata or {}).get("stop") == kind) / len(judged)

    return compute


@metric
def stopped_needlessly() -> Metric:
    """Share of non-failed cases where the agent stopped although it should have answered."""
    return _share(STOPPED_NEEDLESSLY)


@metric
def answered_needlessly() -> Metric:
    """Share of non-failed cases where the agent answered although it should have stopped."""
    return _share(ANSWERED_NEEDLESSLY)


# --- Solver -----------------------------------------------------------------------------------


@solver
def invoke_agent(conductor_for: ConductorFor, agent_id: str, acting_for: Principal) -> Solver:
    """Invoke `agent_id` on the case's input through the conductor, on behalf of `acting_for`
    (whoever runs the evaluation, ADR-0018), and keep the envelope and the linter's report in the
    sample's metadata. No model is called. The profile applied is the one each conductor was
    built with (ADR-0017).

    `conductor_for` runs off Inspect's event loop, since building a conductor may read agent
    cards with an event loop of its own; the invocation is awaited through `Conductor.ainvoke`."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        conductor = await asyncio.to_thread(conductor_for, dict(state.metadata))
        document = json.loads(state.input_text)
        request = InvocationRequest(agent_id=agent_id, input=OpenInput.model_validate(document))
        result = await conductor.ainvoke(request, acting_for=acting_for)
        report = conductor.grounding_reports.get(result.invocation_id)
        envelope = result.to_document()
        state.metadata["envelope"] = envelope
        state.metadata["grounding"] = {
            "passed": report.passed if report else None,
            "violations": list(report.violations) if report else [],
        }
        state.output = ModelOutput.from_content(
            model=agent_id, content=envelope["outcome"]["statement"]
        )
        state.completed = True
        return state

    return solve


# --- Scorers ----------------------------------------------------------------------------------


def envelope_of(state: TaskState) -> dict[str, Any]:
    envelope: dict[str, Any] = state.metadata["envelope"]
    return envelope


def expectation_of(state: TaskState) -> dict[str, Any]:
    expect: dict[str, Any] = state.metadata.get("expect", {})
    return expect


@scorer(metrics=[accuracy()])
def outcome_matches() -> Scorer:
    """The outcome status is the expected one, and so is the reason code if the case names one."""

    async def score(state: TaskState, target: Target) -> Score:
        outcome = envelope_of(state)["outcome"]
        expect = expectation_of(state)
        got = outcome["status"] + (
            f"({outcome['reason_code']})" if "reason_code" in outcome else ""
        )
        ok = outcome["status"] == expect["status"] and (
            "reason_code" not in expect or outcome.get("reason_code") == expect["reason_code"]
        )
        return Score(value=CORRECT if ok else INCORRECT, answer=got)

    return score


@scorer(metrics=[accuracy(), stopped_needlessly(), answered_needlessly()])
def stopped_correctly() -> Scorer:
    """Whether the agent stopped (abstained, referred, suspended) exactly when the case expects
    it to. A `failed` run neither stopped nor answered: it scores incorrect and is left out of
    the two error shares."""

    async def score(state: TaskState, target: Target) -> Score:
        status = envelope_of(state)["outcome"]["status"]
        should_stop = expectation_of(state)["status"] in STOP_STATUSES
        if status == "failed":
            kind = FAILED
        elif status in STOP_STATUSES:
            kind = STOPPED_AS_EXPECTED if should_stop else STOPPED_NEEDLESSLY
        else:
            kind = ANSWERED_NEEDLESSLY if should_stop else ANSWERED_AS_EXPECTED
        ok = kind in (STOPPED_AS_EXPECTED, ANSWERED_AS_EXPECTED)
        return Score(value=CORRECT if ok else INCORRECT, answer=kind, metadata={"stop": kind})

    return score


@scorer(metrics=[accuracy()])
def grounding_passed() -> Scorer:
    """The grounding linter passed the run under the agent's declared mode."""

    async def score(state: TaskState, target: Target) -> Score:
        grounding = state.metadata["grounding"]
        if grounding["passed"] is None:
            return Score(value=NOANSWER, explanation="the conductor kept no linter report")
        return Score(
            value=CORRECT if grounding["passed"] else INCORRECT,
            explanation="; ".join(grounding["violations"]) or "no violations",
        )

    return score


# --- Run identity -----------------------------------------------------------------------------


def git_revision(path: Path) -> str | None:
    """The commit the evaluated code was checked out at, with `+dirty` for uncommitted changes;
    `None` outside a git checkout."""
    try:
        head = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except OSError, subprocess.CalledProcessError:
        return None
    return head + ("+dirty" if dirty else "")


# --- Comparing runs ---------------------------------------------------------------------------

Scores = dict[str, dict[str, float | None]]
"""Per case, per scorer: the score as a float, or `None` where the scorer does not apply."""


def case_scores(log: EvalLog) -> Scores:
    to_float = value_to_float()
    return {
        str(sample.id): {
            name: None if score.value == NOANSWER else to_float(score.value)
            for name, score in (sample.scores or {}).items()
        }
        for sample in log.samples or []
    }


def run_identity(log: EvalLog) -> dict[str, Any]:
    """What produced the run, as the task recorded it in `metadata["identity"]`."""
    ident: dict[str, Any] = (log.eval.metadata or {}).get("identity", {})
    return ident


def baseline_of(log: EvalLog) -> dict[str, Any]:
    return {"task": log.eval.task, "identity": run_identity(log), "scores": case_scores(log)}


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3g}"


def differences(old: Scores, new: Scores) -> tuple[list[str], list[str]]:
    """(regressions, other changes) from `old` to `new`, as readable lines.

    Every score is higher-is-better. A regression is a case missing from `new`, or a score that
    fell or stopped applying. A new case, a rise, or a score that starts to apply is a change."""
    regressions: list[str] = []
    changes: list[str] = []
    for case in sorted(old.keys() | new.keys()):
        if case not in new:
            regressions.append(f"{case}: missing from the new run")
            continue
        if case not in old:
            changes.append(f"{case}: new case")
            continue
        for name in sorted(old[case].keys() | new[case].keys()):
            before, after = old[case].get(name), new[case].get(name)
            if before == after:
                continue
            line = f"{case} {name}: {_fmt(before)} -> {_fmt(after)}"
            if before is not None and (after is None or after < before):
                regressions.append(line)
            else:
                changes.append(line)
    return regressions, changes

"""The Data Management Plan Checker's own scorers: whether it read a plan's commitments as labelled,
proposed none the plan does not make, quoted the plan truly, and flagged what the case expects.

Each is a separate score, never blended with another: a missed commitment, a wrong value and an
invented commitment are different failures, and the last is the worst, since a researcher may
confirm it without checking. A scorer that does not apply to a case returns NOANSWER: the read
scorers on a case that is not a reading, or one that was not read (the template path abstains).
"""

from __future__ import annotations

from typing import Any

from inspect_ai.scorer import CORRECT, INCORRECT, NOANSWER, Score, Scorer, Target, accuracy, scorer
from inspect_ai.solver import TaskState

from dd_agent_advisor_dmp.read_plan import normalise
from workbench.evaluation import envelope_of, expectation_of, mean_applicable

ASPECTS = ("repository", "access", "licence")


def proposed(state: TaskState) -> list[dict[str, Any]] | None:
    """The commitments the checker proposed from reading a plan, or None if this case is not a
    reading or the plan was not read."""
    envelope = envelope_of(state)
    if state.metadata["kind"] != "read" or envelope["outcome"]["status"] != "succeeded":
        return None
    facts: list[dict[str, Any]] = (envelope.get("payload") or {}).get("proposed_facts", [])
    return facts


def labelled(state: TaskState) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = state.metadata["labels"]
    return labels


def names(label: dict[str, Any]) -> set[str]:
    return {normalise(n) for n in [label["output"], *label.get("aliases", [])]}


def label_for(fact: dict[str, Any], labels: list[dict[str, Any]]) -> dict[str, Any] | None:
    subject = normalise(fact["fact_subject"])
    return next((label for label in labels if subject in names(label)), None)


def agrees(label: dict[str, Any], aspect: str, read: str | None) -> bool:
    """Whether a value read agrees with the label: both absent, or the value read contains the
    labelled value, or one of the other forms the label accepts for it, once case, whitespace,
    quotation marks and dashes are set aside. So `open` agrees with `openly available`, and an
    abbreviation the label accepts with the name it stands for."""
    value: str | None = label[aspect]
    if value is None or read is None:
        return value is None and read is None
    forms = [value, *label.get("accept", {}).get(aspect, [])]
    return any(normalise(form) in normalise(read) for form in forms)


@scorer(metrics=[mean_applicable()])
def outputs_recalled() -> Scorer:
    """The share of the plan's labelled commitments the checker proposed, by name or alias. Does
    not apply to a plan that labels none."""

    async def score(state: TaskState, target: Target) -> Score:
        facts, labels = proposed(state), labelled(state)
        if facts is None or not labels:
            return Score(value=NOANSWER, explanation="no labelled commitment was there to read")
        missing = [label["output"] for label in labels if not any(names(label) & _subjects(facts))]
        found = len(labels) - len(missing)
        return Score(
            value=found / len(labels),
            answer=f"{found}/{len(labels)}",
            explanation="missing: " + ", ".join(missing) if missing else "all found",
            metadata={"missing": missing},
        )

    return score


@scorer(metrics=[mean_applicable()])
def aspects_agree() -> Scorer:
    """Of the repository, access and licence of each labelled commitment the checker proposed,
    the share it read as the label gives them, a value the plan does not state counting only if
    it was left empty. Does not apply where no labelled commitment was proposed."""

    async def score(state: TaskState, target: Target) -> Score:
        facts = proposed(state)
        if facts is None:
            return Score(value=NOANSWER, explanation="the plan was not read")
        pairs = [(f, label) for f in facts if (label := label_for(f, labelled(state)))]
        if not pairs:
            return Score(value=NOANSWER, explanation="no labelled commitment was proposed")
        wrong = [
            f"{label['output']} {aspect}: {fact.get(f'commitment_{aspect}')!r}, "
            f"labelled {label[aspect]!r}"
            for fact, label in pairs
            for aspect in ASPECTS
            if not agrees(label, aspect, fact.get(f"commitment_{aspect}"))
        ]
        total = len(pairs) * len(ASPECTS)
        return Score(
            value=(total - len(wrong)) / total,
            answer=f"{total - len(wrong)}/{total}",
            explanation="; ".join(wrong) or "all agree",
            metadata={"wrong": wrong},
        )

    return score


@scorer(metrics=[accuracy()])
def no_unlabelled_commitment() -> Scorer:
    """The checker proposed no commitment the plan does not make: every output it proposed is a
    labelled one. Proposing nothing passes."""

    async def score(state: TaskState, target: Target) -> Score:
        facts = proposed(state)
        if facts is None:
            return Score(value=NOANSWER, explanation="the plan was not read")
        extra = sorted(f["fact_subject"] for f in facts if label_for(f, labelled(state)) is None)
        return Score(
            value=INCORRECT if extra else CORRECT,
            answer=str(len(extra)),
            explanation="not labelled: " + ", ".join(extra) if extra else "none",
            metadata={"unlabelled": extra},
        )

    return score


@scorer(metrics=[accuracy()])
def quotes_found() -> Scorer:
    """Every proposed commitment names the attached plan and quotes words that are in it."""

    async def score(state: TaskState, target: Target) -> Score:
        facts = proposed(state)
        if facts is None:
            return Score(value=NOANSWER, explanation="the plan was not read")
        documents: dict[str, str] = state.metadata["documents"]
        unfound = [
            f["fact_subject"]
            for f in facts
            if normalise(f.get("commitment_quote") or "")
            not in normalise(documents.get(f.get("commitment_document") or "", ""))
            or not f.get("commitment_quote")
        ]
        return Score(
            value=INCORRECT if unfound else CORRECT,
            answer=str(len(unfound)),
            explanation="quote not in the plan: " + ", ".join(unfound) if unfound else "all found",
        )

    return score


@scorer(metrics=[accuracy()])
def discrepancies_match() -> Scorer:
    """The checker flagged exactly the (output, aspect) differences the case expects. Applies to
    a comparison only."""

    async def score(state: TaskState, target: Target) -> Score:
        expect = expectation_of(state)
        envelope = envelope_of(state)
        if "discrepancies" not in expect or envelope["outcome"]["status"] != "succeeded":
            return Score(value=NOANSWER, explanation="the case compares nothing")
        wanted = {(normalise(o), a) for o, a in expect["discrepancies"]}
        found = {
            (normalise(d["output"]), d["aspect"])
            for d in (envelope.get("payload") or {}).get("discrepancies", [])
        }
        missed, extra = sorted(wanted - found), sorted(found - wanted)
        said = [f"missed {o} {a}" for o, a in missed] + [f"extra {o} {a}" for o, a in extra]
        return Score(
            value=CORRECT if not said else INCORRECT,
            answer=f"{len(found & wanted)}/{len(wanted)}",
            explanation="; ".join(said) or "as expected",
        )

    return score


def _subjects(facts: list[dict[str, Any]]) -> set[str]:
    return {normalise(f["fact_subject"]) for f in facts}

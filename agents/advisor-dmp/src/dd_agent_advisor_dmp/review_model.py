"""Reviewers: a model's reading of an attached plan against the core requirements and good
practice (`review.py`, `review_prompt.md`, docs/specs/agents.md, Model-backed personas).

The review has no rules to fall back on: `TemplateReviewer` reads nothing and says no model is
configured, and the agent abstains. `ModelReviewer` gives the model the requirements with their
questions, the decisions people in the project made, and the plan, and the reply is constrained to
a schema (`ReviewReply`). What it says is checked before it is used (`merged`):

- it names a requirement by an id it was given, once;
- it gives a reason;
- where it says the plan answers a requirement, wholly or in part, it gives a quote, and the quote
  is found in the plan once case, whitespace, quotation marks and dashes are set aside.

A reading that passes becomes a finding: `fully` is `covered`, `partly` is `vague` and `not` is
`missing`. A reading that fails is dropped and said, and its requirement has no finding.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dd_agent_advisor_dmp.classes import SectionFinding
from dd_agent_advisor_dmp.match import _unfenced
from dd_agent_advisor_dmp.read_plan import MAX_PLAN, normalise
from dd_agent_advisor_dmp.review import Plan, decisions_of
from dd_dmp_template import SECTIONS, Section
from dd_sdk.agent import RunContext
from dd_sdk.contract.facts import ProjectFact
from dd_sdk.model import CallOptions, Model, ModelCallError, ModelOutputError, Usage, call
from dd_sdk.prompts import ModelCallLog

REVIEW_PROMPT = Path(__file__).with_name("review_prompt.md").read_text(encoding="utf-8").strip()
# The most of a reason kept, in characters.
MAX_REASON = 600
COVERED = (
    "A model read the plan as answering this specifically enough: {reason} Check it against: "
    "{questions}"
)
VAGUE = (
    "A model read the plan as answering this only in part, or in general terms: {reason} Check "
    "it, and answer what it leaves out: {questions}"
)
MISSING = "A model read the plan as not answering this: {reason} A plan should answer: {questions}"
MESSAGES = {"covered": COVERED, "vague": VAGUE, "missing": MISSING}
FINDING_OF = {"fully": "covered", "partly": "vague", "not": "missing"}


class _Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reading(_Reply):
    """The model's reading of one requirement. Every field is required, as a provider's strict
    schema needs."""

    requirement: str
    answered: Literal["fully", "partly", "not"]
    quote: str | None
    reason: str


class ReviewReply(_Reply):
    readings: list[Reading]


@dataclass(frozen=True)
class ModelReview:
    """What a reviewer's model said and the checks kept."""

    findings: list[SectionFinding] = field(default_factory=list)
    dropped: tuple[str, ...] = ()
    # Why the reply as a whole was not used, if so.
    unused: str | None = None
    model_id: str | None = None
    # Whether the plan was cut short to fit.
    cut: bool = False
    usage: Usage = field(default_factory=Usage)
    calls: ModelCallLog | None = None


class Reviewer(Protocol):
    model_id: str | None

    def review(
        self, plan: Plan, decisions: Sequence[ProjectFact], ctx: RunContext
    ) -> ModelReview: ...


class TemplateReviewer:
    """Reads nothing: no model is configured, so there is no review."""

    model_id: str | None = None

    def review(self, plan: Plan, decisions: Sequence[ProjectFact], ctx: RunContext) -> ModelReview:
        return ModelReview()


class ModelReviewer:
    """Reads a plan against the core requirements with the model the agent's settings name, or a
    `dd_sdk.testing.FakeModel` in tests."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self.model_id: str | None = model.model_id

    def review(self, plan: Plan, decisions: Sequence[ProjectFact], ctx: RunContext) -> ModelReview:
        text = plan.text[:MAX_PLAN]
        cut = len(text) < len(plan.text)
        log = ModelCallLog(self.model.provider)
        messages = [{"role": "user", "content": prompt(text, decisions_of(decisions), cut=cut)}]
        try:
            reply = call(
                self.model,
                ctx,
                system=REVIEW_PROMPT,
                messages=messages,
                schema=ReviewReply,
                options=CallOptions(calls=log),
            )
        except ModelCallError as error:
            why = f"the model could not be reached ({error})"
            return ModelReview(unused=why, model_id=self.model_id, cut=cut, calls=log)
        except ModelOutputError as error:
            got = error.reply
            try:
                parsed = ReviewReply.model_validate_json(_unfenced(got.text))
            except ValidationError:
                why = "the model's reply did not match its schema"
                return ModelReview([], (), why, got.model_id, cut, got.usage, got.calls)
            return _used(
                parsed, text, ModelReview([], (), None, got.model_id, cut, got.usage, got.calls)
            )
        if reply.parsed is None:
            why = "the model declined"
            return ModelReview([], (), why, reply.model_id, cut, reply.usage, reply.calls)
        return _used(
            reply.parsed,
            text,
            ModelReview([], (), None, reply.model_id, cut, reply.usage, reply.calls),
        )


def _used(reply: ReviewReply, text: str, given: ModelReview) -> ModelReview:
    """A reply's findings that pass the checks; unused as a whole if none does. `given` carries
    what the call returned: the model, whether the plan was cut, usage and the calls."""
    findings, dropped = merged(reply, text)
    why = None if findings else "none of its readings could be used"
    return replace(given, findings=findings, dropped=dropped, unused=why)


def prompt(text: str, decisions: Sequence[Mapping[str, str]], *, cut: bool) -> str:
    """The user message: the requirements with their questions, the decisions made in the project,
    then the plan, as JSON."""
    requirements = [
        {"requirement": s.id, "heading": s.heading, "questions": list(s.questions)}
        for s in SECTIONS
    ]
    plan = {"text": text, **({"cut": True} if cut else {})}
    return (
        "The core requirements, as JSON:\n"
        + json.dumps(requirements, ensure_ascii=False, indent=1)
        + "\n\nThe decisions people in the project have made, as JSON:\n"
        + json.dumps(list(decisions), ensure_ascii=False, indent=1)
        + "\n\nThe plan the researcher attached, as JSON:\n"
        + json.dumps(plan, ensure_ascii=False)
    )


def merged(reply: ReviewReply, text: str) -> tuple[list[SectionFinding], tuple[str, ...]]:
    """A finding for each reading that passes the checks, in the requirements' order, and why any
    others were not used."""
    ids = {s.id: s for s in SECTIONS}
    plan = normalise(text)
    dropped: list[str] = []
    seen: set[str] = set()
    found: dict[str, SectionFinding] = {}
    for reading in reply.readings:
        why = _unusable(reading, ids, seen, plan)
        seen.add(reading.requirement)
        if why:
            dropped.append(f"{reading.requirement}: {why}")
            continue
        found[reading.requirement] = finding(ids[reading.requirement], reading)
    for section in SECTIONS:
        if section.id not in seen:
            dropped.append(f"{section.id}: not read")
    return [found[s.id] for s in SECTIONS if s.id in found], tuple(dropped)


def _unusable(reading: Reading, ids: Mapping[str, object], seen: set[str], plan: str) -> str | None:
    if reading.requirement not in ids:
        return "names a requirement it was not given"
    if reading.requirement in seen:
        return "read twice"
    if not reading.reason.strip():
        return "gives no reason"
    if reading.answered != "not" and not (reading.quote and reading.quote.strip()):
        return "says the plan answers it but quotes nothing"
    if reading.quote is not None and normalise(reading.quote) not in plan:
        return "quotes words that are not in the plan"
    return None


def finding(section: Section, reading: Reading) -> SectionFinding:
    """One requirement's finding from a reading that passed the checks."""
    reason = " ".join(reading.reason.split())[:MAX_REASON]
    if not reason.endswith((".", "?", "!")):
        reason += "."
    kind = FINDING_OF[reading.answered]
    return SectionFinding(
        section=section.heading,
        finding=kind,
        quote=" ".join(reading.quote.split()) if reading.quote else None,
        message=MESSAGES[kind].format(reason=reason, questions=" ".join(section.questions)),
        reason=reason,
    )

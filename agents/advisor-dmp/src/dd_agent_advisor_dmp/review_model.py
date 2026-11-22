"""Reviewers: a model's reading of an attached plan against the core requirements' questions
(`review.py`, docs/specs/agents.md, Model-backed personas).

`TemplateReviewer` reads nothing, and the rules' review stands. `ModelReviewer` gives the model the
plan, the requirements with their questions and the rules' finding for each, and the reply is
constrained to a schema (`ReviewReply`). What it says is checked before it is used (`merged`):

- it names a requirement by an id it was given, once;
- a quote is found in the plan once case, whitespace, quotation marks and dashes are set aside;
- it gives a reason.

A reading that passes may only raise a finding: a `covered` requirement the model reads as not
answering its questions becomes `vague`, with the model's reason and quote, and a `missing` one
the model finds answered under another heading stays `missing`, with the model's reason and quote,
so that a person judges it. A rule's finding is never lowered. Anything else is dropped and said.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dd_agent_advisor_dmp.classes import SectionFinding
from dd_agent_advisor_dmp.match import _unfenced
from dd_agent_advisor_dmp.read_plan import MAX_PLAN, normalise
from dd_dmp_template import SECTIONS
from dd_sdk.agent import RunContext
from dd_sdk.contract.facts import ProjectDocument
from dd_sdk.contract.models import Derivation
from dd_sdk.model import CallOptions, Model, ModelCallError, ModelOutputError, Usage, call
from dd_sdk.prompts import ModelCallLog

REVIEW_PROMPT = Path(__file__).with_name("review_prompt.md").read_text(encoding="utf-8").strip()
# The most of a reason kept, in characters.
MAX_REASON = 400
VAGUE = (
    "The plan has a section for this, '{heading}', but a model read it as not answering the "
    "requirement's questions: {reason} Check it, and answer what it leaves out."
)
ELSEWHERE = (
    "No heading of the plan names this requirement, but a model read it as answered elsewhere in "
    "the plan: {reason} Check whether it answers: {questions}"
)


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

    findings: list[SectionFinding]
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
        self, plan: ProjectDocument, findings: list[SectionFinding], ctx: RunContext
    ) -> ModelReview: ...


class TemplateReviewer:
    """Reads nothing: the rules' review stands."""

    model_id: str | None = None

    def review(
        self, plan: ProjectDocument, findings: list[SectionFinding], ctx: RunContext
    ) -> ModelReview:
        return ModelReview(findings)


class ModelReviewer:
    """Reads a plan against the core requirements with the model the agent's settings name, or a
    `dd_sdk.testing.FakeModel` in tests."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self.model_id: str | None = model.model_id

    def review(
        self, plan: ProjectDocument, findings: list[SectionFinding], ctx: RunContext
    ) -> ModelReview:
        text = plan.documentation_text[:MAX_PLAN]
        cut = len(text) < len(plan.documentation_text)
        log = ModelCallLog(self.model.provider)
        messages = [{"role": "user", "content": prompt(text, findings, cut=cut)}]
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
            return ModelReview(findings, unused=why, model_id=self.model_id, cut=cut, calls=log)
        except ModelOutputError as error:
            got = error.reply
            try:
                parsed = ReviewReply.model_validate_json(_unfenced(got.text))
            except ValidationError:
                why = "the model's reply did not match its schema"
                return ModelReview(findings, (), why, got.model_id, cut, got.usage, got.calls)
            kept, dropped = merged(parsed, findings, text)
            return ModelReview(kept, dropped, None, got.model_id, cut, got.usage, got.calls)
        if reply.parsed is None:
            return ModelReview(
                findings, (), "the model declined", reply.model_id, cut, reply.usage, reply.calls
            )
        kept, dropped = merged(reply.parsed, findings, text)
        return ModelReview(kept, dropped, None, reply.model_id, cut, reply.usage, reply.calls)


def prompt(text: str, findings: Sequence[SectionFinding], *, cut: bool) -> str:
    """The user message: the requirements with their questions and the rules' findings, then the
    plan, as JSON."""
    by_heading = {f.section: f for f in findings}
    requirements = [
        {
            "requirement": s.id,
            "heading": s.heading,
            "questions": list(s.questions),
            "found_by_headings": by_heading[s.heading].finding,
        }
        for s in SECTIONS
    ]
    plan = {"text": text, **({"cut": True} if cut else {})}
    return (
        "The core requirements, as JSON:\n"
        + json.dumps(requirements, ensure_ascii=False, indent=1)
        + "\n\nThe plan the researcher attached, as JSON:\n"
        + json.dumps(plan, ensure_ascii=False)
    )


def merged(
    reply: ReviewReply, findings: Sequence[SectionFinding], text: str
) -> tuple[list[SectionFinding], tuple[str, ...]]:
    """The findings with the model's readings that pass the checks, and why any others were
    not used. A reading may only raise a finding."""
    ids = {s.id: s for s in SECTIONS}
    plan = normalise(text)
    by_heading = {f.section: f for f in findings}
    dropped: list[str] = []
    seen: set[str] = set()
    for reading in reply.readings:
        why = _unusable(reading, ids, seen, plan)
        seen.add(reading.requirement)
        if why:
            dropped.append(f"{reading.requirement}: {why}")
            continue
        section = ids[reading.requirement]
        found = by_heading[section.heading]
        raised = _raised(found, reading, " ".join(section.questions))
        if raised is not None:
            by_heading[section.heading] = raised
    return [by_heading[f.section] for f in findings], tuple(dropped)


def _unusable(reading: Reading, ids: Mapping[str, object], seen: set[str], plan: str) -> str | None:
    if reading.requirement not in ids:
        return "names a requirement it was not given"
    if reading.requirement in seen:
        return "read twice"
    if not reading.reason.strip():
        return "gives no reason"
    if reading.quote is not None and normalise(reading.quote) not in plan:
        return "quotes words that are not in the plan"
    return None


def _raised(found: SectionFinding, reading: Reading, questions: str) -> SectionFinding | None:
    """`found` raised by the model's reading, or None if the reading changes nothing."""
    reason = " ".join(reading.reason.split())[:MAX_REASON]
    if not reason.endswith((".", "?", "!")):
        reason += "."
    quote = " ".join(reading.quote.split()) if reading.quote else None
    if found.finding == "covered" and reading.answered != "fully":
        return found.model_copy(
            update={
                "finding": "vague",
                "quote": quote or found.quote,
                "message": VAGUE.format(heading=found.plan_heading, reason=reason),
                "finding_derivation": Derivation.MODEL,
                "reason": reason,
            }
        )
    if found.finding == "missing" and reading.answered != "not" and quote:
        # Pointed out, not settled: the finding stays missing for a person to judge.
        return found.model_copy(
            update={
                "quote": quote,
                "message": ELSEWHERE.format(reason=reason, questions=questions),
                "reason": reason,
            }
        )
    return None

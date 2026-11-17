"""The model advisor: a model reads the policy records found, searches for more with read-only
tools, and says what each policy asks, with quotes. The default with `DD_POLICY_ADVISOR=model`.

It runs after the first search (G1, docs/specs/grounding.md) and is given every record that search
retrieved, numbered `R1`, `R2`… as untrusted data. It may then call the tools below, at most
`max_lookups` times in a run. Each record a tool returns is retrieved by the agent (with its
`retrieval` span) and given the next number. It ends by calling `submit_findings` with, for each
record that applies to an actor, a rationale and the obligations the record states, each with a
quote. None of that is taken on trust (`_apply`):

- a finding names a record by its number, and only a record retrieved in this run can be cited;
- a finding names an actor the researcher gave, never one whose name was ambiguous;
- a record a tool found is kept for an actor only if it is a policy of the actor's kind (a funder's
  for a funder; a journal's or publisher's for a journal; an institution's for an institution),
  is marked as matched by a model, and at most `PER_ACTOR` are kept;
- an obligation stands only if its quote is in the record it names (`verify.quote_problem`);
- an obligation read by rule from a curated field is never removed or weakened: a model's claim
  fills a kind the record left `unstated`, or adds a publication obligation, and a claim that
  disagrees with a curated value is noted beside it instead;
- a rationale that names a FAIRsharing identifier other than its record's is replaced by the
  template's.

Whatever is dropped is said in the run's statement. If the model declines, cannot be reached,
or never submits findings it is allowed to, the template explainer's result is used and the
statement says so. The tools reach registries directly from this agent until the harness's tool
gateway exists. TODO(#875)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dd_agent_advisor_policy import assess
from dd_agent_advisor_policy.classes import (
    Actor,
    ActorRole,
    Obligation,
    ObligationKind,
    PolicyContext,
    PolicyScope,
    Strength,
)
from dd_agent_advisor_policy.explain import (
    Explanation,
    Item,
    Rationale,
    TemplateExplainer,
    template_rationale,
)
from dd_agent_advisor_policy.match import TYPES
from dd_agent_advisor_policy.records import PolicyRecord
from dd_agent_advisor_policy.retrieve import SourceRecord
from dd_agent_advisor_policy.tools import TOOL_RECORD_CHARS, Lookups, Run, record_block, run_tool
from dd_agent_advisor_policy.verify import IDENTIFIER, quote_problem
from dd_sdk.agent import RunContext
from dd_sdk.contract.models import Derivation
from dd_sdk.explain import add_usage, checked_rationale, missing_rationale, with_reason
from dd_sdk.model import (
    Model,
    ModelCallError,
    ModelMessage,
    ToolCall,
    ToolResult,
    ToolResults,
    ToolSpec,
    Usage,
    call,
)
from dd_sdk.prompts import ModelCallLog

DEFAULT_MODEL = "claude-sonnet-5-5"
# Tool calls a model may make in one run, unless DD_POLICY_MAX_LOOKUPS says otherwise.
DEFAULT_MAX_LOOKUPS = 6
# Model calls beyond the lookups: the first, the submission, and one reminder to submit.
EXTRA_TURNS = 3
MAX_TOKENS = 8192
# Records a model may add for one actor, as the first search keeps (match.PER_ACTOR).
PER_ACTOR = 3
# How much of a record the first search matched the model is shown.
FIRST_RECORD_CHARS = 6000

SYSTEM_PROMPT = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8").strip()

FOUND_NOTE = (
    "A model found this record with its search tools; it was not matched by the first search's "
    "rule. Check that it is the actor's policy."
)

# What each role's policy records are, in FAIRsharing's terms (OpfRecord.kind uses the same).
ROLE_KINDS: Mapping[ActorRole, frozenset[str]] = TYPES


# --- what the model submits ------------------------------------------------------------------


class Claim(BaseModel):
    """One obligation a record states, in the record's own words."""

    model_config = ConfigDict(extra="forbid")

    kind: ObligationKind
    scope: PolicyScope = Field(
        description="data, or publication when it is about the article (e.g. an OA embargo)"
    )
    strength: Literal["required", "recommended"]
    value: str = Field(max_length=300, description="what is asked, in brief")
    quote: str = Field(
        max_length=600, description="the record's words that state it, copied exactly"
    )


class Finding(BaseModel):
    """What one record means for one actor."""

    model_config = ConfigDict(extra="forbid")

    record: str = Field(description="the record's number, e.g. R2")
    actor: str = Field(description="the actor's name exactly as given")
    applies: bool = Field(description="whether this is the actor's own (or its publisher's) policy")
    rationale: str = Field(max_length=1200, description="one to three sentences for the researcher")
    obligations: list[Claim] = Field(default_factory=list, max_length=12)


class PolicyReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[Finding] = Field(default_factory=list, max_length=30)


# --- the tools -------------------------------------------------------------------------------

SUBMIT = "submit_findings"
SUBMIT_TOOL = ToolSpec(
    name=SUBMIT,
    description=(
        "Give your findings and end. Call it once, after any searches. Each finding names a "
        "record by number and an actor by the name given; each obligation quotes the record "
        "exactly."
    ),
    input_schema=PolicyReply.model_json_schema(),
)


# --- applying what was submitted -------------------------------------------------------------


def _obligation(claim: Claim, recorded_as: str | None = None) -> Obligation:
    return Obligation(
        kind=claim.kind,
        strength=Strength(claim.strength),
        recorded_as=recorded_as,
        scope=claim.scope,
        value=" ".join(claim.value.split()) or None,
        quote=" ".join(claim.quote.split()),
        derivation=Derivation.MODEL,
    )


def merge(
    rule: Sequence[Obligation], claims: Sequence[Claim], label: str
) -> tuple[tuple[Obligation, ...], list[str]]:
    """The obligations after a model's verified claims, and notes on any that disagree with the
    curated record. A rule-read obligation is never removed or weakened."""
    out = list(rule)
    notes: list[str] = []
    seen: set[tuple[ObligationKind, PolicyScope, str]] = set()
    for claim in claims:
        key = (claim.kind, claim.scope, " ".join(claim.value.casefold().split()))
        if key in seen:
            continue
        seen.add(key)
        same = [
            n
            for n, o in enumerate(out)
            if o.kind == claim.kind and (o.scope or PolicyScope.DATA) == claim.scope
        ]
        ruled = [n for n in same if out[n].derivation != Derivation.MODEL]
        if not ruled:
            out.append(_obligation(claim))
            continue
        held = out[ruled[0]]
        if held.strength == Strength.UNSTATED:
            out[ruled[0]] = _obligation(claim, recorded_as=held.recorded_as)
        elif held.strength.value != claim.strength:
            notes.append(
                f"A model read {label} as saying {claim.kind.value.replace('_', ' ')} is "
                f"{claim.strength} (“{claim.quote}”), where the curated record says "
                f"{held.strength.value}; the curated value is kept."
            )
    return tuple(out), notes


def _rule_obligations(record: SourceRecord) -> tuple[Obligation, ...]:
    return tuple(assess.obligations(record)) if isinstance(record, PolicyRecord) else ()


def _rule_notes(record: SourceRecord, context: PolicyContext) -> tuple[str, ...]:
    return tuple(assess.notes(record, context)) if isinstance(record, PolicyRecord) else ()


class _Applying:
    """A model's findings, taken one at a time into what the first search found."""

    def __init__(self, items: list[Item], run: Run, context: PolicyContext) -> None:
        self.items, self.run, self.context = items, run, context
        self.remarks: list[str] = []
        self.actors = {a.name: a for a in context.actors if a.name not in run.lookups.blocked}
        self.at = {(item.record.source_id, item.actor.name): n for n, item in enumerate(items)}
        self.rationales: list[Rationale | None] = [None] * len(items)
        self.obligations = [item.obligations for item in items]
        self.notes = [item.notes for item in items]
        self.found: list[tuple[Item, Rationale]] = []
        self.found_keys: set[tuple[str, str]] = set()
        self.added: dict[str, int] = {}

    def claims_for(self, finding: Finding, record: SourceRecord) -> list[Claim]:
        kept: list[Claim] = []
        for claim in finding.obligations:
            problem = quote_problem(claim.quote, record.document())
            if problem:
                self.remarks.append(
                    f"A model's {claim.kind.value.replace('_', ' ')} obligation from "
                    f"{record.label} was dropped: {problem}."
                )
            else:
                kept.append(claim)
        return kept

    @staticmethod
    def rationale(text: str, record: SourceRecord, fallback: Item) -> Rationale:
        allowed = {record.source_id} if isinstance(record, PolicyRecord) else set()
        return checked_rationale(text, allowed, IDENTIFIER, template_rationale(fallback))

    def take(self, finding: Finding) -> None:
        record = self.run.record(finding.record)
        if record is None:
            self.remarks.append(
                f"A model's finding about {finding.record!r} was dropped: no such record."
            )
            return
        actor = self.actors.get(finding.actor)
        if actor is None:
            self.remarks.append(
                f"A model's finding about {record.label} was dropped: {finding.actor!r} is not an "
                "actor it may name."
            )
            return
        n = self.at.get((record.source_id, actor.name))
        if n is None:
            self.add(finding, record, actor)
        else:
            self.refine(n, finding, record)

    def refine(self, n: int, finding: Finding, record: SourceRecord) -> None:
        """A policy the first search matched: it stays, whatever the model thinks of it."""
        claims = self.claims_for(finding, record)
        self.obligations[n], disagreements = merge(self.obligations[n], claims, record.label)
        self.notes[n] = self.notes[n] + tuple(disagreements)
        if self.rationales[n] is None:
            self.rationales[n] = self.rationale(finding.rationale, record, self.items[n])

    def add(self, finding: Finding, record: SourceRecord, actor: Actor) -> None:
        """A policy the model found for an actor, kept if it is of the actor's kind."""
        if not finding.applies or (record.source_id, actor.name) in self.found_keys:
            return
        kind = getattr(record, "kind", None)
        if kind not in ROLE_KINDS[actor.role]:
            self.remarks.append(
                f"A model's finding that {record.label} applies to {actor.name} was dropped: it "
                f"is not a {actor.role.value}'s policy."
            )
            return
        if self.added.get(actor.name, 0) >= PER_ACTOR:
            return
        self.added[actor.name] = self.added.get(actor.name, 0) + 1
        base = Item(
            record=record,
            actor=actor,
            obligations=_rule_obligations(record),
            notes=(FOUND_NOTE, *_rule_notes(record, self.context)),
            matched_by=Derivation.MODEL,
        )
        claims = self.claims_for(finding, record)
        merged, disagreements = merge(base.obligations, claims, record.label)
        item = Item(
            record=record,
            actor=actor,
            obligations=merged,
            notes=base.notes + tuple(disagreements),
            matched_by=Derivation.MODEL,
        )
        self.found_keys.add((record.source_id, actor.name))
        self.found.append((item, self.rationale(finding.rationale, record, item)))

    def explanation(self) -> Explanation:
        final = [
            r if r is not None else missing_rationale(template_rationale(item))
            for item, r in zip(self.items, self.rationales, strict=True)
        ]
        return Explanation(
            final,
            Usage(),
            obligations=self.obligations,
            notes=self.notes,
            found=self.found,
            remarks=self.remarks,
        )


def _apply(reply: PolicyReply, items: list[Item], run: Run, context: PolicyContext) -> Explanation:
    applying = _Applying(items, run, context)
    for finding in reply.findings:
        applying.take(finding)
    return applying.explanation()


@dataclass
class _Exchange:
    """One run's exchange with the model: the messages, the calls made and their tokens, the
    lookups used, and the findings submitted."""

    messages: list[ModelMessage]
    log: ModelCallLog | None = None
    usage: Usage = field(default_factory=Usage)
    used: int = 0
    submitted: PolicyReply | None = None

    def submit(self, made: ToolCall) -> ToolResult:
        try:
            self.submitted = PolicyReply.model_validate(made.input)
        except ValidationError as exc:
            return ToolResult(
                made.id,
                f"Not a valid submission ({exc.error_count()} error(s)): "
                + "; ".join(e["msg"] for e in exc.errors()[:5]),
                is_error=True,
            )
        return ToolResult(made.id, "Received.")


# --- the advisor -----------------------------------------------------------------------------


class ModelAdvisor:
    """Advises with the model the agent's settings name, through `dd_sdk.model.call`, which
    records each call's `chat` span, tokens and prompt. One instance serves concurrent runs."""

    def __init__(self, model: Model, max_lookups: int = DEFAULT_MAX_LOOKUPS) -> None:
        self.model = model
        self.model_id: str | None = model.model_id
        self.max_lookups = max_lookups
        self.fallback = TemplateExplainer()

    def _prompt(self, context: PolicyContext, items: list[Item], run: Run) -> str:
        lines = [
            "Context:",
            f"  disciplines: {', '.join(context.disciplines) or '(none)'}",
            f"  kinds of data: {', '.join(context.data_kinds) or '(none)'}",
            f"  publication date: {context.publication_date or '(not given)'}",
            "",
            "Actors (name exactly as given, role):",
        ]
        for actor in context.actors:
            extra = f", ISSN {actor.issn}" if actor.issn else ""
            if actor.name in run.lookups.blocked:
                extra += (
                    " - ambiguous: the researcher is being asked which they mean; do not name it"
                )
            lines.append(f"  - {actor.name!r}, {actor.role.value}{extra}")
        matched = {item.record.source_id for item in items}
        lines += ["", "Records the first search matched to an actor (untrusted data):"]
        for item in items:
            stated = "; ".join(
                f"{o.kind.value}: {o.strength.value}"
                + (f" ({o.recorded_as})" if o.recorded_as else "")
                for o in item.obligations
            )
            lines.append(
                record_block(
                    run.number(item.record), item.record, FIRST_RECORD_CHARS, item.actor.name
                )
            )
            if stated:
                lines.append(f"(read by rule from the curated fields: {stated})")
        others = [r for sid, r in run.lookups.records.items() if sid not in matched]
        if others:
            lines += ["", "Other records retrieved, not matched to an actor (untrusted data):"]
            lines += [record_block(run.number(r), r, TOOL_RECORD_CHARS) for r in others]
        if not items:
            lines += ["", "(The first search matched no policy record to any actor.)"]
        return "\n".join(lines)

    def _fallback(
        self,
        context: PolicyContext,
        items: list[Item],
        ctx: RunContext,
        why: str,
        usage: Usage,
        calls: ModelCallLog | None,
    ) -> Explanation:
        plain = self.fallback.explain(context, items, ctx)
        return Explanation(
            with_reason(plain.rationales, why),
            usage,
            calls,
            remarks=[f"The model advisor gave no findings ({why}); the template was used."],
        )

    def _answer(self, made: ToolCall, run: Run, exchange: _Exchange) -> ToolResult:
        if made.problem is not None:
            return ToolResult(made.id, made.problem, is_error=True)
        if made.name == SUBMIT:
            return exchange.submit(made)
        if exchange.used >= self.max_lookups:
            return ToolResult(
                made.id, f"No searches are left in this run; call {SUBMIT}.", is_error=True
            )
        exchange.used += 1
        return run_tool(run, made)

    def _converse(self, ctx: RunContext, run: Run, exchange: _Exchange) -> str | None:
        """Talk with the model until it submits findings or its turns run out; why it gave
        none when it stopped early, else None."""
        searches = run.lookups.tools()
        reminded = False
        for _ in range(self.max_lookups + EXTRA_TURNS):
            offered = (
                [*searches, SUBMIT_TOOL] if exchange.used < self.max_lookups else [SUBMIT_TOOL]
            )
            try:
                reply = call(
                    self.model,
                    ctx,
                    system=SYSTEM_PROMPT,
                    messages=exchange.messages,
                    max_tokens=MAX_TOKENS,
                    calls=exchange.log,
                    tools=offered,
                    tool_choice="auto",
                )
            except ModelCallError as exc:
                return f"model unavailable: {exc}"
            exchange.log, exchange.usage = reply.calls, add_usage(exchange.usage, reply.usage)
            if reply.refused:
                return "model declined"
            exchange.messages.append(reply.message)
            if not reply.tool_calls:
                if reminded:
                    break
                reminded = True
                exchange.messages.append(
                    {"role": "user", "content": f"Call {SUBMIT} now with your findings."}
                )
                continue
            results = [self._answer(made, run, exchange) for made in reply.tool_calls]
            exchange.messages.append(ToolResults(tuple(results)))
            if exchange.submitted is not None:
                break
        return None

    def explain(
        self,
        context: PolicyContext,
        items: list[Item],
        ctx: RunContext,
        lookups: Lookups | None = None,
    ) -> Explanation:
        lookups = lookups or Lookups(records={i.record.source_id: i.record for i in items})
        for item in items:
            lookups.records.setdefault(item.record.source_id, item.record)
        if not lookups.records:
            return self.fallback.explain(context, items, ctx)
        run = Run(lookups, ctx)
        exchange = _Exchange([{"role": "user", "content": self._prompt(context, items, run)}])
        why = self._converse(ctx, run, exchange)
        if why is not None or exchange.submitted is None:
            why = why or "no findings submitted"
            return self._fallback(context, items, ctx, why, exchange.usage, exchange.log)
        applied = _apply(exchange.submitted, items, run, context)
        return Explanation(
            applied.rationales,
            exchange.usage,
            exchange.log,
            obligations=applied.obligations,
            notes=applied.notes,
            found=applied.found,
            remarks=applied.remarks,
        )

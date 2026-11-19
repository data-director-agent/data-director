"""The model advisor: a model reads the FAIRsharing records found, searches for more with a
read-only tool, and says why each recommendation fits, what else fits, and what it doubts. The
default with `DD_STANDARDS_EXPLAINER=model`, which is on unless an operator turns it off.

It runs after the first search and the ranking (G1, docs/specs/grounding.md) and is given every
record that search retrieved, numbered `S1`, `S2`… as untrusted data, with the rules' picks marked.
It may then call `search_fairsharing`, at most `max_lookups` times in a run. Each record a search
returns is retrieved by the agent (with its `retrieval` span) and given the next number. It ends by
calling `submit_recommendations`. None of that is taken on trust (`_apply`):

- a rationale, addition or concern names a record by its number, and only a record retrieved in
  this run can be cited;
- a rule pick is never removed: the model may write its rationale and note a concern beside it;
- an addition is kept only if its record is not deprecated, its kind fits the record's FAIRsharing
  type (a terminology for a vocabulary or ontology; a model or format for a format), its target is
  the dataset or a field the profile has, it repeats no other recommendation, and no more than
  `max_per_kind` (`ranking.yaml`) were added of its kind;
- a rationale that names a FAIRsharing identifier other than its record's is replaced by the
  template's.

Whatever is dropped is said in the run's statement. If the model declines, cannot be reached, or
never submits, the template explainer's result is used and the statement says so. The search tool
reaches FAIRsharing from this agent, not yet through the harness's tool gateway. TODO(#1143)
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dd_agent_advisor_standards import rank as ranking
from dd_agent_advisor_standards.classes import DatasetProfile, RecommendationKind
from dd_agent_advisor_standards.explain import (
    IDENTIFIER,
    Addition,
    Explanation,
    Item,
    Lookups,
    Rationale,
    TemplateExplainer,
    template_rationale,
)
from dd_agent_advisor_standards.fairsharing.records import MODEL_AND_FORMAT, TERMINOLOGY, Record
from dd_agent_advisor_standards.tools import SEARCH, Run, record_block, run_tool
from dd_sdk.agent import RunContext
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
# Searches a model may make in one run, unless DD_STANDARDS_MAX_LOOKUPS says otherwise.
DEFAULT_MAX_LOOKUPS = 4
# Model calls beyond the searches: the first, the submission, and one reminder to submit.
EXTRA_TURNS = 3
MAX_TOKENS = 8192

SYSTEM_PROMPT = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8").strip()

TERMINOLOGY_KINDS = frozenset(
    {
        RecommendationKind.CONTROLLED_VOCABULARY,
        RecommendationKind.ONTOLOGY,
        RecommendationKind.TERMINOLOGY_UNCLASSIFIED,
    }
)
FORMAT_KINDS = frozenset({RecommendationKind.DATA_FORMAT, RecommendationKind.FIELD_FORMAT})
# The FAIRsharing record type each kind must come from.
RECORD_TYPE = {
    **dict.fromkeys(TERMINOLOGY_KINDS, TERMINOLOGY),
    **dict.fromkeys(FORMAT_KINDS, MODEL_AND_FORMAT),
}


# --- what the model submits ------------------------------------------------------------------


class PickRationale(BaseModel):
    """Why one of the rules' picks fits."""

    model_config = ConfigDict(extra="forbid")

    record: str = Field(description="the record's number, e.g. S2")
    target: str = Field(description="the pick's target as listed: dataset or field:<name>")
    rationale: str = Field(max_length=800, description="one or two sentences for the researcher")


class Concern(BaseModel):
    """Doubt about one of the rules' picks. The pick stays; the concern is shown beside it."""

    model_config = ConfigDict(extra="forbid")

    record: str = Field(description="the record's number, e.g. S2")
    concern: str = Field(max_length=400, description="why it may not suit this dataset")


class AdditionClaim(BaseModel):
    """A record the rules did not pick that suits the dataset."""

    model_config = ConfigDict(extra="forbid")

    record: str = Field(description="the record's number, e.g. S7")
    kind: RecommendationKind
    target: str = Field(description="dataset, or field:<name> for a field_format")
    rationale: str = Field(max_length=800, description="one or two sentences for the researcher")


class StandardsReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rationales: list[PickRationale] = Field(default_factory=list, max_length=40)
    additions: list[AdditionClaim] = Field(default_factory=list, max_length=12)
    concerns: list[Concern] = Field(default_factory=list, max_length=20)


# --- the tools -------------------------------------------------------------------------------

SUBMIT = "submit_recommendations"
SUBMIT_TOOL = ToolSpec(
    name=SUBMIT,
    description=(
        "Give your recommendations and end. Call it once, after any searches. Write a rationale "
        "for each rule pick, add only records that are numbered here, and name a concern for a "
        "rule pick you doubt."
    ),
    input_schema=StandardsReply.model_json_schema(),
)
# --- applying what was submitted -------------------------------------------------------------


def _rationale(text: str, record: Record, fallback: str) -> Rationale:
    return checked_rationale(text, {record.fairsharing_id}, IDENTIFIER, fallback)


def _addition_problem(claim: AdditionClaim, record: Record, profile: DatasetProfile) -> str | None:
    if (record.status or "").lower() == "deprecated":
        return "the record is deprecated"
    wanted = RECORD_TYPE[claim.kind]
    if record.record_type != wanted:
        return f"a {claim.kind.value} must be a FAIRsharing {wanted} record"
    target = claim.target.strip()
    if claim.kind == RecommendationKind.FIELD_FORMAT:
        name = target.removeprefix("field:")
        if not target.startswith("field:") or name not in {f.name for f in profile.fields}:
            return f"{target!r} is not a field of the dataset"
    elif target != "dataset":
        return f"a {claim.kind.value} is for the dataset, not {target!r}"
    return None


def _pick_rationales(
    reply: StandardsReply,
    items: list[Item],
    run: Run,
    at: dict[tuple[str, str], int],
    remarks: list[str],
) -> list[Rationale | None]:
    rationales: list[Rationale | None] = [None] * len(items)
    for given in reply.rationales:
        record = run.record(given.record)
        n = at.get((record.fairsharing_id, given.target.strip())) if record else None
        if record is None or n is None:
            remarks.append(
                f"A model's rationale for {given.record!r} ({given.target}) was dropped: it names "
                "no rule pick."
            )
            continue
        if rationales[n] is None:
            rationales[n] = _rationale(given.rationale, record, template_rationale(*items[n]))
    return rationales


def _pick_concerns(
    reply: StandardsReply, items: list[Item], run: Run, remarks: list[str]
) -> list[str | None]:
    concerns: list[str | None] = [None] * len(items)
    by_record: dict[str, list[int]] = {}
    for at_n, (picked, *_) in enumerate(items):
        by_record.setdefault(picked.fairsharing_id, []).append(at_n)
    for doubt in reply.concerns:
        doubted = run.record(doubt.record)
        picks = by_record.get(doubted.fairsharing_id, []) if doubted else []
        if not picks:
            remarks.append(f"A model's concern about {doubt.record!r} was dropped: no rule pick.")
            continue
        for at_n in picks:
            concerns[at_n] = concerns[at_n] or " ".join(doubt.concern.split())
    return concerns


def _additions(
    reply: StandardsReply,
    profile: DatasetProfile,
    run: Run,
    at: dict[tuple[str, str], int],
    remarks: list[str],
) -> list[Addition]:
    cap = int(ranking.config()["max_per_kind"])
    added: Counter[RecommendationKind] = Counter()
    taken = set(at)
    additions: list[Addition] = []
    for claim in reply.additions:
        found = run.record(claim.record)
        if found is None:
            remarks.append(f"A model's addition {claim.record!r} was dropped: no such record.")
            continue
        key = (found.fairsharing_id, claim.target.strip())
        problem = (
            _addition_problem(claim, found, profile)
            or ("it repeats another recommendation" if key in taken else None)
            or (f"no more than {cap} of a kind may be added" if added[claim.kind] >= cap else None)
        )
        if problem is not None:
            remarks.append(f"A model's addition of {found.name} was dropped: {problem}.")
            continue
        taken.add(key)
        added[claim.kind] += 1
        fallback = template_rationale(found, claim.kind, key[1], ("chosen by a model",))
        additions.append(
            Addition(found, claim.kind, key[1], _rationale(claim.rationale, found, fallback))
        )
    return additions


def _apply(
    reply: StandardsReply, profile: DatasetProfile, items: list[Item], run: Run
) -> Explanation:
    remarks: list[str] = []
    at: dict[tuple[str, str], int] = {
        (record.fairsharing_id, target): n for n, (record, _, target, _) in enumerate(items)
    }
    rationales = _pick_rationales(reply, items, run, at, remarks)
    concerns = _pick_concerns(reply, items, run, remarks)
    additions = _additions(reply, profile, run, at, remarks)
    final = [
        r if r is not None else missing_rationale(template_rationale(*item))
        for item, r in zip(items, rationales, strict=True)
    ]
    return Explanation(final, Usage(), concerns=concerns, additions=additions, remarks=remarks)


@dataclass
class _Exchange:
    """One run's exchange with the model: the messages, the calls made and their tokens, the
    searches offered and used, and the recommendations submitted."""

    messages: list[ModelMessage]
    searches: list[ToolSpec]
    log: ModelCallLog | None = None
    usage: Usage = field(default_factory=Usage)
    used: int = 0
    submitted: StandardsReply | None = None

    def submit(self, made: ToolCall) -> ToolResult:
        try:
            self.submitted = StandardsReply.model_validate(made.input)
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

    def _prompt(self, profile: DatasetProfile, items: list[Item], run: Run) -> str:
        lines = [
            "Dataset profile (metadata only, never data values):",
            f"  title: {profile.title or '(none)'}",
            f"  description: {profile.description or '(none)'}",
            f"  keywords: {', '.join(profile.keywords) or '(none)'}",
            f"  themes: {', '.join(profile.themes) or '(none)'}",
            f"  media types: {', '.join(profile.media_types) or '(none)'}",
            "  fields: "
            + (
                ", ".join(f"{f.name} ({f.field_type or 'unknown'})" for f in profile.fields)
                or "(none)"
            ),
        ]
        picks: dict[str, list[str]] = {}
        for record, kind, target, _ in items:
            picks.setdefault(record.fairsharing_id, []).append(f"{kind.value} for {target}")
        lines += ["", "Records the rules picked (untrusted data):"]
        for rid in picks:
            record = run.lookups.records[rid]
            lines.append(record_block(run.number(record), record, picks[rid]))
        others = [r for rid, r in run.lookups.records.items() if rid not in picks]
        if others:
            lines += ["", "Other records the first search retrieved (untrusted data):"]
            lines += [record_block(run.number(r), r) for r in others]
        return "\n".join(lines)

    def _fallback(
        self,
        profile: DatasetProfile,
        items: list[Item],
        ctx: RunContext,
        why: str,
        usage: Usage,
        calls: ModelCallLog | None,
    ) -> Explanation:
        plain = self.fallback.explain(profile, items, ctx)
        return Explanation(
            with_reason(plain.rationales, why),
            usage,
            calls,
            remarks=[f"The model advisor gave no recommendations ({why}); the template was used."],
        )

    def _answer(self, made: ToolCall, run: Run, exchange: _Exchange) -> ToolResult:
        if made.problem is not None:
            return ToolResult(made.id, made.problem, is_error=True)
        if made.name == SUBMIT:
            return exchange.submit(made)
        if exchange.used >= self.max_lookups or not exchange.searches:
            return ToolResult(
                made.id, f"No searches are left in this run; call {SUBMIT}.", is_error=True
            )
        exchange.used += 1
        return run_tool(run, made)

    def _converse(self, ctx: RunContext, run: Run, exchange: _Exchange) -> str | None:
        """Talk with the model until it submits recommendations or its turns run out; why it
        gave none when it stopped early, else None."""
        reminded = False
        for _ in range(self.max_lookups + EXTRA_TURNS):
            offered = (
                [*exchange.searches, SUBMIT_TOOL]
                if exchange.used < self.max_lookups
                else [SUBMIT_TOOL]
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
                exchange.messages.append({"role": "user", "content": f"Call {SUBMIT} now."})
                continue
            results = [self._answer(made, run, exchange) for made in reply.tool_calls]
            exchange.messages.append(ToolResults(tuple(results)))
            if exchange.submitted is not None:
                break
        return None

    def explain(
        self,
        profile: DatasetProfile,
        items: list[Item],
        ctx: RunContext,
        lookups: Lookups | None = None,
    ) -> Explanation:
        lookups = lookups or Lookups()
        for record, *_ in items:
            lookups.records.setdefault(record.fairsharing_id, record)
        if not items:
            return self.fallback.explain(profile, items, ctx)
        run = Run(lookups, ctx)
        exchange = _Exchange(
            [{"role": "user", "content": self._prompt(profile, items, run)}],
            [SEARCH] if lookups.retrieval is not None and self.max_lookups > 0 else [],
        )
        why = self._converse(ctx, run, exchange)
        if why is not None or exchange.submitted is None:
            why = why or "no recommendations submitted"
            return self._fallback(profile, items, ctx, why, exchange.usage, exchange.log)
        applied = _apply(exchange.submitted, profile, items, run)
        return Explanation(
            applied.rationales,
            exchange.usage,
            exchange.log,
            concerns=applied.concerns,
            additions=applied.additions,
            remarks=applied.remarks,
        )

"""Stage 4 — explain (§5.4). Wired and callable; never reached on a v0.1 run.

This stage writes what a reader sees: why each candidate was recommended and what part of the
dataset it applies to. The model is given the profile, the top ranked candidates *with their
full registry records and score breakdowns*, and the reasoning behind the ranking.

Two design points are implemented rather than deferred, because both are cheap now and awkward
later:

- **The prompt is loaded from the versioned library and its reference is recorded** on the stage
  report, which is how §5.4's "recorded with each run" reaches the output document.
- **Only column metadata is sent.** `_profile_digest` builds the model's view of the dataset from
  names, inferred types and counts. Sample values are deliberately excluded — §1.4 makes that a
  constraint on the design, not a note about test data, so the exclusion belongs in the code
  that builds the prompt rather than in a reviewer's memory.

The three prohibitions in the prompt are enforced by checking the output afterwards (§5.5), not
by trusting the model to obey them.

On a v0.1 run the candidate set is always empty, so no model call happens and no key is needed.
The stage is still exercised by `test_explain_node` against a stocked fake registry and a fake
model, which is what keeps the model seam honest before a real registry exists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from standards_advisor.llm.structured import call_structured
from standards_advisor.models.candidates import Explanation, RankedCandidate
from standards_advisor.models.common import StageName, StageStatus
from standards_advisor.models.profile import DatasetProfile
from standards_advisor.models.recommendations import Evidence, Target, TargetKind
from standards_advisor.nodes.support import merge, stage

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

    from standards_advisor.context import RunContext
    from standards_advisor.state import PipelineState

PROMPT_NAME = "explain"

# How many ranked candidates per kind are explained. §5.4 says "the top few": explaining a long
# tail costs tokens and produces recommendations nobody reads.
TOP_N_PER_KIND = 3

# How many of a column's declared permitted values are shown to the model. Enough to convey what
# kind of thing the column names, which is what R3.1 matches on, without letting one large code
# list crowd out the rest of the profile.
PERMITTED_VALUES_SHOWN = 24


class _DraftEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str
    record: str
    field: str


class _Draft(BaseModel):
    """What the model is asked to return for one candidate."""

    model_config = ConfigDict(extra="forbid")

    registry_id: str
    reason: str
    target_field: str | None = None
    target_detail: str | None = None
    caveats: list[str] = Field(default_factory=list)
    evidence: list[_DraftEvidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class _Drafts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explanations: list[_Draft] = Field(default_factory=list)


def explain_node(state: PipelineState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = runtime.context
    profile = state.get("profile")
    ranked_set = state.get("ranked")

    with stage(ctx, StageName.EXPLAIN) as run:
        shortlist = _shortlist(ranked_set)

        if profile is None or not shortlist:
            run.status = StageStatus.EMPTY
            run.note("no ranked candidates to explain; no model was called")
            run.payload = []
            return_value: list[Explanation] = []
        else:
            prompt = ctx.prompts.get(PROMPT_NAME)
            ctx.run_dir.copy_prompt(prompt.name, prompt.version, prompt.text)
            run.prompts = [prompt.ref()]
            run.model_id = ctx.model_id
            run.model_params = ctx.model_params_as_strings()

            result = call_structured(
                ctx.model(),
                _Drafts,
                [("system", prompt.text), ("human", _render(profile, shortlist))],
            )

            if not result.ok:
                # A parse failure is data, not a crash. The run continues and the check stage
                # will report every kind as unexplained.
                run.fail("explain_unparsed", result.parse_error or "unknown parse failure")
                ctx.events.note("explain_unparsed", result.parse_error or "unknown")
                run.status = StageStatus.DEGRADED
                run.payload = []
                return_value = []
            else:
                explanations = _to_explanations(result.parsed, shortlist, run)
                run.payload = explanations
                run.counts = {
                    "candidates_sent": len(shortlist),
                    "explanations": len(explanations),
                }
                return_value = explanations

    return merge(run, explanations=return_value)


def _shortlist(ranked_set: Any) -> list[RankedCandidate]:
    """The top few per kind, so one prolific kind cannot crowd out the others."""
    if ranked_set is None:
        return []
    result: list[RankedCandidate] = []
    seen: dict[str, int] = {}
    for item in ranked_set.ranked:
        kind = item.candidate.kind.value
        if seen.get(kind, 0) >= TOP_N_PER_KIND:
            continue
        seen[kind] = seen.get(kind, 0) + 1
        result.append(item)
    return result


def _profile_digest(profile: DatasetProfile) -> str:
    """The model's view of the dataset. **The §1.4 chokepoint.**

    Two categories of column information are permitted here and one is not, and the line between
    them is the whole of §1.4 as amended by §8:

    - **Permitted:** names, inferred and declared types, patterns, units, counts, and a data
      dictionary's *declared* `permitted_values` and `description`. All of these are schema —
      statements the researcher wrote about what the data will contain.
    - **Never:** `example_values`. Those are observed values read out of a real file, and no
      amount of usefulness makes them metadata.

    `test_sample_values_are_never_put_in_the_prompt` and its `permitted_values` sibling are the
    only mechanical guard on that boundary, so anything added to this function needs one.
    """
    lines = [
        f"Phase: {profile.phase.value}",
        f"Title: {profile.title or '(none supplied)'}",
        f"Abstract: {profile.abstract or '(none supplied)'}",
        f"Keywords: {', '.join(profile.keywords) or '(none)'}",
        f"Formats found: {', '.join(profile.formats_found) or '(none detected)'}",
        f"Formats planned: {', '.join(profile.formats_planned) or '(none stated)'}",
        f"Subjects: {', '.join(term.term for term in profile.subjects) or '(none)'}",
        f"Missing value codes: {', '.join(profile.missing_value_codes) or '(none declared)'}",
        "",
        "Columns (name | type | pattern | unit | blanks | distinct | permitted values):",
    ]
    for column in profile.columns:
        lines.append(
            f"- {column.name} | {column.inferred_type.value} | {column.pattern or '-'} "
            f"| {column.unit or '-'} | {_percent(column.blank_proportion)} "
            f"| {_count(column.distinct_count)} | {_permitted(column.permitted_values)}"
        )
        if column.description:
            lines.append(f"    definition: {column.description}")
    return "\n".join(lines)


def _percent(value: float | None) -> str:
    """A proportion, or `-` where nothing was measured. `None` means no data was read (§8)."""
    return "-" if value is None else f"{value:.0%}"


def _count(value: int | None) -> str:
    return "-" if value is None else str(value)


def _permitted(values: list[str]) -> str:
    """A column's declared permitted values, truncated.

    Truncated rather than omitted: a long code list is still evidence of what kind of thing the
    column names, which is what R3.1 matches on, and the count tells the model the list went on.
    """
    if not values:
        return "-"
    if len(values) <= PERMITTED_VALUES_SHOWN:
        return ", ".join(values)
    shown = ", ".join(values[:PERMITTED_VALUES_SHOWN])
    return f"{shown}, ... ({len(values)} in total)"


def _render(profile: DatasetProfile, shortlist: list[RankedCandidate]) -> str:
    """The human message: the dataset, then the candidates with records and score breakdowns."""
    blocks = [_profile_digest(profile), "", "Candidates:"]
    for item in shortlist:
        resource = item.candidate.resource
        blocks.append(
            f"\n[{item.candidate.kind.value}] {resource.name} ({resource.registry_id})\n"
            f"  status: {resource.status or 'unknown'}  "
            f"subtype: {resource.record_subtype or 'unknown'}\n"
            f"  score: {item.score:.3f}\n"
            f"  score breakdown: "
            + (
                ", ".join(
                    f"{component.name}={component.raw:.3f}"
                    f" x {component.weight:.2f} ({component.source})"
                    for component in item.components
                )
                or "no rule produced a score"
            )
            + f"\n  rules skipped for missing inputs: {', '.join(item.skipped_rules) or 'none'}\n"
            f"  record fields: "
            + (
                "; ".join(f"{key}={value}" for key, value in sorted(item.candidate.record.items()))
                or "(none supplied by this route)"
            )
        )
    return "\n".join(blocks)


def _to_explanations(
    drafts: _Drafts | None, shortlist: list[RankedCandidate], run: Any
) -> list[Explanation]:
    """Convert drafts to `Explanation`s, dropping any that names an unknown candidate.

    This is not the §5.5 grounding check — that runs over the whole output and is the
    non-negotiable one. This is the cheap local version: a draft whose `registry_id` was not in
    the set we sent cannot be matched to a kind or a target, so there is nothing to carry
    forward. It is recorded as a failure so the two are distinguishable in the run record.
    """
    if drafts is None:
        return []
    by_id = {item.candidate.resource.registry_id: item for item in shortlist}
    explanations: list[Explanation] = []
    for draft in drafts.explanations:
        item = by_id.get(draft.registry_id)
        if item is None:
            run.fail(
                "explain_unknown_candidate",
                f"model named {draft.registry_id!r}, which was not in the candidate set",
            )
            continue
        explanations.append(
            Explanation(
                registry_id=draft.registry_id,
                kind=item.candidate.kind,
                target=_target(draft, item),
                reason=draft.reason,
                caveats=list(draft.caveats),
                evidence=[
                    Evidence(statement=e.statement, record=e.record, field=e.field)
                    for e in draft.evidence
                ],
                confidence=draft.confidence,
            )
        )
    return explanations


def _target(draft: _Draft, item: RankedCandidate) -> Target:
    """Take the field the model named, but keep the *kind* the retriever assigned.

    The model is asked which part of the dataset a recommendation applies to, not what sort of
    thing that part is — the retriever already knows, because it chose the target when it built
    the query. Overriding the kind with `FIELD_VALUES` whenever a field was named got two cases
    wrong: an ontology recommendation would be labelled as applying to a column's values, which
    is precisely the confusion §2.1 forbids, and a pre-collection recommendation about a planned
    variable would be labelled as though the values already existed (§8).
    """
    existing = item.candidate.targets[0] if item.candidate.targets else None
    if draft.target_field:
        return Target(
            kind=existing.kind if existing is not None else TargetKind.FIELD_VALUES,
            field=draft.target_field,
            file=existing.file if existing is not None else None,
            detail=draft.target_detail,
        )
    if existing is not None:
        return existing
    return Target(kind=TargetKind.DATASET, detail=draft.target_detail)

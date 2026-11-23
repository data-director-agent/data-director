"""The Standards Librarian: retrieve → rank → advise over FAIRsharing.

Grounding invariant: retrieval and ranking precede any model call. The rules' picks always stand.
A model (`advise.ModelAdvisor`, on by default) writes their rationales, may note a concern beside
one, and may add recommendations, each naming a record retrieved in this run, its own searches
included; the agent checks every addition before it is kept. The linter checks the trace
afterwards (mode `retrieval`: G1-G4).

A recommendation names its record once, in `grounded_on`. What the reader is shown about the record
(name, status, DOI) is the evidence item's `content`: the projection its hash covers, which the
linter re-hashes (E1, docs/specs/grounding.md). There is no second copy to disagree with the first.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from dd_agent_advisor_standards import propose
from dd_agent_advisor_standards import rank as ranking
from dd_agent_advisor_standards.classes import (
    DatasetProfile,
    Recommendation,
    RecommendationKind,
    Recommendations,
    SearchedSummary,
)
from dd_agent_advisor_standards.decided import filled, said
from dd_agent_advisor_standards.explain import Explainer, Lookups, TemplateExplainer
from dd_agent_advisor_standards.fairsharing.records import Record
from dd_agent_advisor_standards.fairsharing.snapshot import SnapshotBackend
from dd_agent_advisor_standards.retrieve import RetrievalAdapter
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext, abstain
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    EvidenceItem,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)
from dd_sdk.evidence import CANONICALISATION, HASH_ALGORITHM, project
from dd_sdk.registry import Hit, Query, RegistryUnavailable, SnapshotRef, provenance
from dd_sdk.tracing import retrieval_span

FOUND_NOTE = (
    "A model chose this record from those retrieved in this run; the ranking rules did not. "
    "Check that it suits the dataset."
)

# What the payload says it does not yet do: the curated subtype is TODO(#4), the gateway
# TODO(#1143).
LIMITATIONS = [
    "Whether a terminology is a vocabulary or an ontology is read from its name and description, "
    "not from FAIRsharing's curated subtype.",
    "The ranking is lexical. A model, when one is configured, may add what it misses but its "
    "choices have not yet been evaluated.",
    "A model's searches reach FAIRsharing from this agent, not through the harness's tool gateway.",
]


class StandardsAgent:
    spec = AgentSpec(
        agent_id="advisor.standards",
        title="Standards Librarian",
        icon="📚",
        version="0.6.0",
        description=(
            "Recommends controlled vocabularies, ontologies and data formats from FAIRsharing "
            "for a dataset profile, whether its data are collected or still being planned, "
            "grounded on the registry records it retrieved. Ranking rules "
            "choose first; a model may add records it found and note doubts, never remove one. "
            "Each recommendation is proposed for the researcher to choose in their project."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(DatasetProfile),),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload=ClassSchema.of(Recommendations),
        derivations={
            "items.kind": Derived(Derivation.LEXICAL, recorded_in="classification_derivation"),
            "items.target": Derived(Derivation.LEXICAL, recorded_in="selection_derivation"),
            "items.rationale": Derived(Derivation.MODEL, recorded_in="rationale_derivation"),
            "items.concern": Derived(Derivation.MODEL),
            "items.notes": Derived(Derivation.TEMPLATE),
            "limitations": Derived(Derivation.TEMPLATE),
            "searched.from_project_record": Derived(Derivation.TEMPLATE),
        },
        serves=("setup.formats", "preparation.formats", "preparation.vocabularies"),
    )

    def __init__(
        self,
        retrieval: RetrievalAdapter,
        explainer: Explainer | None = None,
        fallback: RetrievalAdapter | None = None,
    ) -> None:
        self.retrieval = retrieval
        self.fallback = fallback
        self.explainer = explainer or TemplateExplainer()

    # --- retrieval ------------------------------------------------------------------------

    def _search_all(
        self, queries: list[Query], ctx: RunContext
    ) -> tuple[dict[str, list[Hit[Record]]], SnapshotRef, dict[str, Record], RetrievalAdapter]:
        adapter = self.retrieval
        ref = adapter.snapshot_ref()
        results: dict[str, list[Hit[Record]]] = {}
        retrieved: dict[str, Record] = {}
        try:
            for q in queries:
                results[q.label] = adapter.search(q)
        except RegistryUnavailable as exc:
            if self.fallback is None or isinstance(adapter, SnapshotBackend):
                raise
            adapter = self.fallback
            ref = SnapshotRef(
                label=adapter.snapshot_ref().label, stale=True, notes=[f"live route failed: {exc}"]
            )
            results = {q.label: adapter.search(q) for q in queries}
        # One retrieval span per distinct record: this is the evidence the linter matches on.
        for hits in results.values():
            for hit in hits:
                rec = hit.record
                if rec.fairsharing_id in retrieved:
                    continue
                retrieved[rec.fairsharing_id] = rec
                with retrieval_span(ctx.tracer, rec.fairsharing_id, rec.content_hash()):
                    pass
        return results, ref, retrieved, adapter

    # --- assembly -------------------------------------------------------------------------

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        # Which copy answered for each record the live route returned: FAIRsharing itself or
        # the local cache (docs/specs/grounding.md).
        with provenance.observed() as origins:
            return self._run(request, ctx, origins)

    def _run(
        self, request: InvocationRequest, ctx: RunContext, origins: provenance.Provenance
    ) -> AgentResult:
        asked = request.input
        assert isinstance(asked, DatasetProfile)  # the conductor checked spec.accepts
        # What the input leaves empty is filled from what people in the project decided (#1529).
        profile, from_record = filled(asked)
        queries = ranking.build_queries(profile)
        if not queries:
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                (
                    "The dataset profile has no title, keywords, themes, media types or "
                    "temporal fields to search on, and the project has no decided field of "
                    "study, so no registry query was possible."
                ),
            )

        try:
            results, ref, retrieved, adapter = self._search_all(queries, ctx)
        except RegistryUnavailable as exc:
            return abstain(
                ReasonCode.REGISTRY_UNAVAILABLE,
                (f"FAIRsharing could not be searched: {exc}. This is not an empty result."),
            )

        # Notes count only if the live route answered; the fallback re-reads every record.
        noted = origins if adapter is self.retrieval else provenance.Provenance()
        searched = SearchedSummary(
            queries=[q.describe() for q in queries],
            snapshot_ref="; ".join(sorted({noted.ref(rid, ref).as_string() for rid in retrieved}))
            or ref.as_string(),
            candidates_retrieved=len(retrieved),
            from_project_record=from_record,
        )
        if not retrieved:
            return abstain(
                ReasonCode.NO_CANDIDATES_RETRIEVED,
                f"FAIRsharing ({ref.as_string()}) returned nothing for: "
                + "; ".join(searched.queries),
            )

        # Rank per query, keep qualifying, cap per (query, kind), dedupe across queries. The cap
        # is per query so a media-type query contributes its own format candidates rather than
        # being crowded out by the subject query; a field-format query yields at most one.
        cap = int(ranking.config()["max_per_kind"])
        chosen: list[ranking.Ranked] = []
        seen: set[tuple[RecommendationKind, str]] = set()
        for q in queries:
            taken: dict[RecommendationKind, int] = defaultdict(int)
            limit = 1 if q.label.startswith("field-format") else cap
            for r in ranking.qualifying(ranking.rank(q, results.get(q.label, []), profile)):
                key = (r.kind, r.hit.record.fairsharing_id)
                if key in seen or taken[r.kind] >= limit:
                    continue
                seen.add(key)
                taken[r.kind] += 1
                chosen.append(r)
        searched = searched.model_copy(update={"candidates_qualifying": len(chosen)})

        if not chosen:
            return abstain(
                ReasonCode.NO_QUALIFYING_RESOURCE,
                f"{len(retrieved)} FAIRsharing records were retrieved "
                f"({ref.as_string()}) but none scored at or above the confidence "
                f"floor of {ranking.config()['confidence_floor']}. "
                "Searched: " + "; ".join(searched.queries),
            )

        # Field-level targets: one recommendation per temporal field for the ISO 8601 hit.
        expanded: list[tuple[ranking.Ranked, str]] = []
        temporal_fields = [
            f.name for f in profile.fields if (f.field_type or "").lower() in ranking.TEMPORAL_TYPES
        ]
        for r in chosen:
            if r.kind == RecommendationKind.FIELD_FORMAT:
                expanded.extend((r, f"field:{name}") for name in temporal_fields)
            else:
                expanded.append((r, "dataset"))

        # Advise — after retrieval and ranking. A model's searches add to `retrieved`, each with
        # its retrieval span, so whatever it adds is cited from a retrieved record.
        explanation = self.explainer.explain(
            profile,
            [(r.hit.record, r.kind, target, r.reasons) for r, target in expanded],
            ctx,
            Lookups(retrieval=adapter, records=retrieved),
        )
        concerns = list(explanation.concerns) or [None] * len(expanded)

        now = datetime.now(UTC)
        items: list[Recommendation] = []
        for (r, target), rationale, concern in zip(
            expanded, explanation.rationales, concerns, strict=True
        ):
            rec = r.hit.record
            grounding = GroundingRef(source_id=rec.fairsharing_id, content_hash=rec.content_hash())
            items.append(
                Recommendation(
                    kind=r.kind,
                    target=target,
                    score=r.score,
                    rationale=rationale.text,
                    rationale_derivation=rationale.derivation,
                    classification_derivation=r.classification_derivation,
                    selection_derivation=Derivation.LEXICAL,
                    concern=concern,
                    grounded_on=[grounding],
                )
            )
        for addition in explanation.additions:
            rec = addition.record
            items.append(
                Recommendation(
                    kind=addition.kind,
                    target=addition.target,
                    rationale=addition.rationale.text,
                    rationale_derivation=addition.rationale.derivation,
                    classification_derivation=Derivation.MODEL,
                    selection_derivation=Derivation.MODEL,
                    notes=[FOUND_NOTE],
                    grounded_on=[
                        GroundingRef(source_id=rec.fairsharing_id, content_hash=rec.content_hash())
                    ],
                )
            )
        cited = {g.source_id for i in items for g in i.grounded_on}
        evidence = [
            EvidenceItem(
                source_id=rec.fairsharing_id,
                source_uri=rec.source_uri or rec.url,
                retrieved_at=noted.ref(rid, ref).retrieved_at or now,
                snapshot_ref=noted.ref(rid, ref).as_string(),
                hash_algorithm=HASH_ALGORITHM,
                canonicalisation=CANONICALISATION,
                content_hash=rec.content_hash(),
                content=project(rec.hash_projection()),
            )
            for rid, rec in sorted(retrieved.items())
            if rid in cited
        ]
        grounded_on = [
            GroundingRef(source_id=e.source_id, content_hash=e.content_hash) for e in evidence
        ]
        kinds = sorted({i.kind.value for i in items})
        added = (
            f" {len(explanation.additions)} of them added by a model."
            if explanation.additions
            else ""
        )
        remarks = "".join(f" {r}" for r in explanation.remarks) + said(from_record)
        payload = Recommendations(
            items=items,
            searched=searched,
            grounded_on=grounded_on,
            limitations=LIMITATIONS,
            proposed_facts=propose.proposals(items, retrieved, ref.as_string()),
        )
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"{len(items)} recommendation(s) across {', '.join(kinds)}, grounded in "
                    f"{len(evidence)} FAIRsharing record(s) ({ref.as_string()}).{added}{remarks} "
                    "Human review is required."
                ),
            ),
            payload=payload,
            evidence=evidence,
            model_id=self.explainer.model_id,
            input_tokens=explanation.usage.input_tokens,
            output_tokens=explanation.usage.output_tokens,
            model_calls=explanation.calls.calls if explanation.calls else (),
            prompts=explanation.calls.prompts if explanation.calls else {},
        )

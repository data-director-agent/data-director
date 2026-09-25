"""The R3 agent: retrieve → rank → explain over FAIRsharing.

Grounding invariant: retrieval precedes any model call, and the model never determines the
identity of a recommendation. The explainer sees already-ranked records and writes rationale;
the workbench's linter checks the trace afterwards (mode `retrieval`: G1-G4).

A recommendation names its record once, in `grounded_on`. What the reader is shown about the
record (name, status, DOI) is the evidence item's `content`: the projection its hash covers,
which the linter re-hashes (E1, ADR-0015). There is no second copy to disagree with the first.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from dd_agent_r3 import rank as ranking
from dd_agent_r3.explain import Explainer, TemplateExplainer
from dd_agent_r3.fairsharing.records import Record
from dd_agent_r3.fairsharing.snapshot import SnapshotBackend
from dd_agent_r3.retrieve import (
    Hit,
    Query,
    RegistryUnavailable,
    RetrievalAdapter,
    SnapshotRef,
)
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    DatasetProfile,
    Derivation,
    EvidenceItem,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    Recommendation,
    RecommendationKind,
    Recommendations,
    SearchedSummary,
)
from dd_sdk.evidence import CANONICALISATION, HASH_ALGORITHM, project
from dd_sdk.tracing import retrieval_span


class R3Agent:
    spec = AgentSpec(
        agent_id="r3.standards-advisor",
        version="0.2.0",
        description=(
            "Recommends controlled vocabularies, ontologies and data formats from FAIRsharing "
            "for a dataset profile, grounded on the registry records it retrieved."
        ),
        requirement_ids=("R3", "R3.1", "R3.2", "R3.3", "R3.4", "R3.5", "R3.6"),
        action_class="advise",
        accepts=(ClassSchema.of(DatasetProfile),),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload=ClassSchema.of(Recommendations),
        derivations={
            "items.kind": Derived(Derivation.LEXICAL, recorded_in="classification_derivation"),
            "items.rationale": Derived(Derivation.MODEL, recorded_in="rationale_derivation"),
        },
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
    ) -> tuple[dict[str, list[Hit]], SnapshotRef, dict[str, Record]]:
        adapter = self.retrieval
        ref = adapter.snapshot_ref()
        results: dict[str, list[Hit]] = {}
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
        return results, ref, retrieved

    # --- assembly -------------------------------------------------------------------------

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        profile = request.input
        assert isinstance(profile, DatasetProfile)  # the conductor checked spec.accepts
        queries = ranking.build_queries(profile)
        if not queries:
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.INSUFFICIENT_INPUT,
                    statement=(
                        "The dataset profile has no title, keywords, themes, media types or "
                        "temporal fields to search on, so no registry query was possible."
                    ),
                )
            )

        try:
            results, ref, retrieved = self._search_all(queries, ctx)
        except RegistryUnavailable as exc:
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.REGISTRY_UNAVAILABLE,
                    statement=(
                        f"FAIRsharing could not be searched: {exc}. This is not an empty result."
                    ),
                )
            )

        searched = SearchedSummary(
            queries=[q.describe() for q in queries],
            snapshot_ref=ref.as_string(),
            candidates_retrieved=len(retrieved),
        )
        if not retrieved:
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.NO_CANDIDATES_RETRIEVED,
                    statement=f"FAIRsharing ({ref.as_string()}) returned nothing for: "
                    + "; ".join(searched.queries),
                )
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
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.NO_QUALIFYING_RESOURCE,
                    statement=(
                        f"{len(retrieved)} FAIRsharing records were retrieved "
                        f"({ref.as_string()}) but none scored at or above the confidence "
                        f"floor of {ranking.config()['confidence_floor']}. "
                        "Searched: " + "; ".join(searched.queries)
                    ),
                )
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

        # Explain — after retrieval, over decided identities only.
        explanation = self.explainer.explain(
            profile, [(r.hit.record, r.kind, target, r.reasons) for r, target in expanded], ctx
        )

        now = datetime.now(UTC)
        items: list[Recommendation] = []
        for (r, target), rationale in zip(expanded, explanation.rationales, strict=True):
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
                    grounded_on=[grounding],
                )
            )
        cited = {g.source_id for i in items for g in i.grounded_on}
        evidence = [
            EvidenceItem(
                source_id=rec.fairsharing_id,
                source_uri=rec.source_uri or rec.url,
                retrieved_at=now,
                snapshot_ref=ref.as_string(),
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
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"{len(items)} recommendation(s) across {', '.join(kinds)}, grounded in "
                    f"{len(evidence)} FAIRsharing record(s) ({ref.as_string()}). "
                    "Human review is required."
                ),
            ),
            payload=Recommendations(items=items, searched=searched, grounded_on=grounded_on),
            evidence=evidence,
            model_id=self.explainer.model_id,
            input_tokens=explanation.usage.input_tokens,
            output_tokens=explanation.usage.output_tokens,
        )

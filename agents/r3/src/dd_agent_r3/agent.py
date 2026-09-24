"""The R3 agent: retrieve → rank → explain over FAIRsharing.

Grounding invariant: retrieval precedes any model call, and the model never determines the
identity of a recommendation. The explainer sees already-ranked records and writes rationale;
`grounding.lint` checks the trace afterwards.
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
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import (
    DatasetProfile,
    EvidenceItem,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    Recommendation,
    RecommendationKind,
    Recommendations,
    ResourceRef,
    SearchedSummary,
)
from dd_sdk.evidence import CANONICALISATION, HASH_ALGORITHM
from dd_sdk.tracing import retrieval_span


class R3Agent:
    agent_id = "r3.standards-advisor"
    version = "0.1.0"
    requirement_ids: tuple[str, ...] = ("R3", "R3.1", "R3.2", "R3.3", "R3.4", "R3.5", "R3.6")
    action_class = "advise"

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
        # TODO: R3 is not yet ported to the generalised interface (see factory.py); until then it
        # narrows the polymorphic input itself.
        assert isinstance(request.input, DatasetProfile)
        profile: DatasetProfile = request.input
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
        rationales = self.explainer.explain(
            profile, [(r.hit.record, r.kind, target, r.reasons) for r, target in expanded], ctx
        )

        now = datetime.now(UTC)
        items: list[Recommendation] = []
        for (r, target), rationale in zip(expanded, rationales, strict=True):
            rec = r.hit.record
            items.append(
                Recommendation(
                    kind=r.kind,
                    target=target,
                    resource=ResourceRef(
                        fairsharing_id=rec.fairsharing_id,
                        doi=rec.doi,
                        name=rec.name,
                        url=rec.url,
                        record_type=rec.record_type,
                        status=rec.status,
                    ),
                    score=r.score,
                    rationale=rationale.text,
                    rationale_derivation=rationale.derivation,
                    classification_derivation=r.classification_derivation,
                    evidence_hashes=[rec.content_hash()],
                )
            )
        cited = {i.resource.fairsharing_id for i in items}
        evidence = [
            EvidenceItem(
                source_id=rec.fairsharing_id,
                source_uri=rec.source_uri or rec.url,
                retrieved_at=now,
                snapshot_ref=ref.as_string(),
                hash_algorithm=HASH_ALGORITHM,
                canonicalisation=CANONICALISATION,
                content_hash=rec.content_hash(),
            )
            for rid, rec in sorted(retrieved.items())
            if rid in cited
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
            payload=Recommendations(items=items, searched=searched),
            evidence=evidence,
            model_id=self.explainer.model_id,
            input_tokens=self.explainer.usage.input_tokens,
            output_tokens=self.explainer.usage.output_tokens,
        )

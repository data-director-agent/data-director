"""The repository advisor: retrieve → assess → rank → explain, over re3data and FAIRsharing.

It serves four steps of Phase 3 (Figure 3): recommending a repository (R1), whether it assigns
persistent identifiers (R7), its access options and costs, and its certification. Whether a
repository is mandated is a policy question, answered by `policy.advisor` from policy records
(its `PolicyChecks.mandated_repositories`); the orchestrator passes the answer in as
`RepositoryNeeds.mandated`. With mandated repositories the agent describes them, flagging the
needs they do not meet; with none it shortlists. The researcher chooses (TODO(#199)).

Grounding invariant: retrieval precedes any model call, and the model never determines which
repositories are offered or any judgement about them. A candidate names its records once, in
`grounded_on`; what the reader is shown about them is the evidence items' `content`, which the
linter re-hashes (E1, ADR-0015).
"""

from __future__ import annotations

from datetime import UTC, datetime

from dd_agent_repository import assess, rank
from dd_agent_repository.classes import (
    CandidateBasis,
    RepositoryCandidate,
    RepositoryNeeds,
    RepositoryOptions,
    SearchedSummary,
)
from dd_agent_repository.explain import Explainer, Item, TemplateExplainer
from dd_agent_repository.records import DatabaseRecord, Re3dataRecord
from dd_agent_repository.retrieve import (
    Databases,
    RegistryUnavailable,
    Repositories,
    SnapshotRef,
)
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
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
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, HASH_ALGORITHM
from dd_sdk.tracing import retrieval_span


def _abstain(reason: ReasonCode, statement: str) -> AgentResult:
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.ABSTAINED, reason_code=reason, statement=statement)
    )


class _Retrieved:
    """The records one run retrieved, and which copy of each registry answered."""

    def __init__(self, re3data_ref: SnapshotRef) -> None:
        self.re3data_ref = re3data_ref
        self.repositories: dict[str, Re3dataRecord] = {}
        # Each FAIRsharing record with the copy that answered for it: the live route may fail
        # part-way through a run, after which the snapshot answers.
        self.databases: dict[str, tuple[DatabaseRecord, SnapshotRef]] = {}
        self.databases_down = False

    def summary(self) -> str:
        refs = [self.re3data_ref.as_string()]
        refs += sorted({ref.as_string() for _, ref in self.databases.values()})
        return "; ".join(refs)


class RepositoryAgent:
    spec = AgentSpec(
        agent_id="repository.advisor",
        version="0.1.0-alpha",
        description=(
            "Recommends data repositories from re3data, or describes the ones mandated, with "
            "their persistent identifiers, access, costs and certification as the registries "
            "record them. The researcher chooses."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(RepositoryNeeds),),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload=ClassSchema.of(RepositoryOptions),
        derivations={
            "candidates.assigns_pids": Derived(Derivation.REGISTRY),
            "candidates.commercial": Derived(Derivation.REGISTRY),
            "candidates.fee_required": Derived(Derivation.REGISTRY),
            "candidates.meets": Derived(Derivation.TEMPLATE),
            "candidates.misses": Derived(Derivation.TEMPLATE),
            "candidates.notes": Derived(Derivation.TEMPLATE),
            "candidates.rationale": Derived(Derivation.MODEL, recorded_in="rationale_derivation"),
        },
        serves=(
            "repository.recommend",
            "repository.pid",
            "repository.access-and-costs",
            "repository.certification",
        ),
    )

    def __init__(
        self,
        repositories: Repositories,
        databases: Databases | None = None,
        explainer: Explainer | None = None,
        fallback: Repositories | None = None,
        databases_fallback: Databases | None = None,
    ) -> None:
        self.repositories = repositories
        self.databases = databases
        self.fallback = fallback
        self.databases_fallback = databases_fallback
        self.explainer = explainer or TemplateExplainer()

    # --- retrieval ------------------------------------------------------------------------

    def _from_re3data(
        self, needs: RepositoryNeeds, source: Repositories
    ) -> tuple[list[Re3dataRecord], list[str], dict[str, float], dict[str, Re3dataRecord]]:
        """Mandated records and the names not found, or the shortlist's hits."""
        mandated: list[Re3dataRecord] = []
        not_found: list[str] = []
        subject_scores: dict[str, float] = {}
        hits: dict[str, Re3dataRecord] = {}
        for ref in needs.mandated:
            record = source.fetch(ref.re3data_id) if ref.re3data_id else source.find(ref.name)
            if record is None:
                not_found.append(ref.name)
            elif record.re3data_id not in {m.re3data_id for m in mandated}:
                mandated.append(record)
        if not needs.mandated:
            for query in rank.queries(needs):
                found = source.search(query)
                for hit in found:
                    hits.setdefault(hit.record.re3data_id, hit.record)
                if query.label == "subject":
                    for rid, fit in rank.fit(found).items():
                        subject_scores[rid] = max(fit, subject_scores.get(rid, 0.0))
        return mandated, not_found, subject_scores, hits

    def _database(self, fairsharing_id: str, got: _Retrieved) -> None:
        """Fetch the FAIRsharing record re3data cross-references. Optional: if FAIRsharing cannot
        be asked, the candidate stands on its re3data record alone."""
        if self.databases is not None and not got.databases_down:
            try:
                record = self.databases.fetch(fairsharing_id)
            except RegistryUnavailable:
                got.databases_down = True
            else:
                if record is not None:
                    got.databases[fairsharing_id] = (record, self.databases.snapshot_ref())
                return
        if self.databases_fallback is not None:
            try:
                record = self.databases_fallback.fetch(fairsharing_id)
            except RegistryUnavailable:
                return
            if record is not None:
                ref = self.databases_fallback.snapshot_ref()
                got.databases[fairsharing_id] = (record, SnapshotRef(label=ref.label, stale=True))

    # --- assembly -------------------------------------------------------------------------

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        needs = request.input
        assert isinstance(needs, RepositoryNeeds)  # the conductor checked spec.accepts
        if not (needs.mandated or rank.queries(needs)):
            return _abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "The needs name no mandated repository, no theme or kind of data, and no "
                "affiliation, so there was nothing to look up.",
            )

        source = self.repositories
        got = _Retrieved(source.snapshot_ref())
        try:
            mandated, not_found, subject_scores, hits = self._from_re3data(needs, source)
        except RegistryUnavailable as exc:
            if self.fallback is None:
                return _abstain(
                    ReasonCode.REGISTRY_UNAVAILABLE,
                    f"re3data could not be searched: {exc}. This is not an empty result.",
                )
            try:
                mandated, not_found, subject_scores, hits = self._from_re3data(needs, self.fallback)
            except RegistryUnavailable as again:
                return _abstain(
                    ReasonCode.REGISTRY_UNAVAILABLE,
                    f"re3data could not be searched ({exc}), nor its snapshot ({again}).",
                )
            got.re3data_ref = SnapshotRef(
                label=self.fallback.snapshot_ref().label,
                stale=True,
                notes=[f"live route failed: {exc}"],
            )
        for record in [*mandated, *hits.values()]:
            got.repositories[record.re3data_id] = record
        for record in got.repositories.values():
            if record.fairsharing_id and record.fairsharing_id not in got.databases:
                self._database(record.fairsharing_id, got)
        # One retrieval span per record: this is the evidence the linter matches on.
        for rid, repository in got.repositories.items():
            with retrieval_span(ctx.tracer, rid, repository.content_hash()):
                pass
        for fid, (database, _) in got.databases.items():
            with retrieval_span(ctx.tracer, fid, database.content_hash()):
                pass

        queries = [f"mandated: {r.name!r}" for r in needs.mandated] or [
            q.describe() for q in rank.queries(needs)
        ]
        searched = SearchedSummary(
            queries=queries,
            snapshot_ref=got.summary(),
            candidates_retrieved=len(got.repositories),
        )

        chosen: list[tuple[Re3dataRecord, CandidateBasis, float | None, tuple[str, ...]]]
        if needs.mandated:
            if not mandated:
                return _abstain(
                    ReasonCode.NO_CANDIDATES_RETRIEVED,
                    f"No re3data record was found for {', '.join(not_found)} "
                    f"({got.summary()}). Check the names, or give the re3data identifiers.",
                )
            chosen = [(r, CandidateBasis.MANDATED, None, ()) for r in mandated]
        else:
            if not hits:
                return _abstain(
                    ReasonCode.NO_CANDIDATES_RETRIEVED,
                    f"re3data ({got.summary()}) returned nothing for: " + "; ".join(queries),
                )
            ranked = rank.rank(subject_scores, hits, needs)
            if not ranked:
                return _abstain(
                    ReasonCode.NO_QUALIFYING_RESOURCE,
                    f"{len(hits)} repositories were retrieved ({got.summary()}) but none "
                    f"reached the floor of {rank.config()['confidence_floor']} or accepts "
                    "deposits. Searched: " + "; ".join(queries),
                )
            chosen = [(r.record, CandidateBasis.RECOMMENDED, r.score, r.reasons) for r in ranked]
        searched = searched.model_copy(update={"candidates_qualifying": len(chosen)})

        items: list[Item] = []
        for record, basis, _, reasons in chosen:
            pair = got.databases.get(record.fairsharing_id or "")
            cross = pair[0] if pair else None
            items.append(
                Item(
                    record=record,
                    database=cross,
                    basis=basis,
                    assessment=assess.assess(record, cross, needs),
                    reasons=reasons,
                )
            )
        # Explain — after retrieval, over decided candidates only.
        explanation = self.explainer.explain(needs, items, ctx)

        candidates: list[RepositoryCandidate] = []
        for item, (_, _, score, _), rationale in zip(
            items, chosen, explanation.rationales, strict=True
        ):
            grounded = [
                GroundingRef(
                    source_id=item.record.re3data_id, content_hash=item.record.content_hash()
                )
            ]
            if item.database is not None:
                grounded.append(
                    GroundingRef(
                        source_id=item.database.fairsharing_id,
                        content_hash=item.database.content_hash(),
                    )
                )
            candidates.append(
                RepositoryCandidate(
                    basis=item.basis,
                    score=score,
                    assigns_pids=assess.assigns_pids(item.record),
                    commercial=assess.commercial(item.record),
                    fee_required=assess.fee_required(item.record),
                    meets=item.assessment.meets,
                    misses=item.assessment.misses,
                    notes=item.assessment.notes,
                    rationale=rationale.text,
                    rationale_derivation=rationale.derivation,
                    grounded_on=grounded,
                )
            )

        evidence = self._evidence(candidates, got)
        grounded_on = [
            GroundingRef(source_id=e.source_id, content_hash=e.content_hash) for e in evidence
        ]
        done = "mandated, described" if needs.mandated else "recommended"
        statement = (
            f"Repositories {done}: {len(candidates)}, grounded in {len(evidence)} registry "
            f"record(s) ({got.summary()})."
        )
        short = [c for c in candidates if c.basis == CandidateBasis.MANDATED and c.misses]
        if short:
            statement += (
                f" Mandated repositories that do not meet, or do not state, every need: "
                f"{len(short)}; see each candidate's misses."
            )
        if not_found:
            statement += f" No record found for: {', '.join(not_found)}."
        statement += " The researcher chooses; human review is required."
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
            payload=RepositoryOptions(
                candidates=candidates,
                not_found=not_found,
                searched=searched,
                grounded_on=grounded_on,
            ),
            evidence=evidence,
            model_id=self.explainer.model_id,
            input_tokens=explanation.usage.input_tokens,
            output_tokens=explanation.usage.output_tokens,
        )

    def _evidence(
        self, candidates: list[RepositoryCandidate], got: _Retrieved
    ) -> list[EvidenceItem]:
        now = datetime.now(UTC)
        cited = {g.source_id for c in candidates for g in c.grounded_on}
        out: list[EvidenceItem] = []
        for rid, repository in sorted(got.repositories.items()):
            if rid in cited:
                out.append(
                    EvidenceItem(
                        source_id=rid,
                        source_uri=repository.source_uri,
                        retrieved_at=now,
                        snapshot_ref=got.re3data_ref.as_string(),
                        hash_algorithm=HASH_ALGORITHM,
                        canonicalisation=DOCUMENT_CANONICALISATION,
                        content_hash=repository.content_hash(),
                        content=repository.document(),
                    )
                )
        for fid, (database, ref) in sorted(got.databases.items()):
            if fid in cited:
                out.append(
                    EvidenceItem(
                        source_id=fid,
                        source_uri=database.source_uri,
                        retrieved_at=now,
                        snapshot_ref=ref.as_string(),
                        hash_algorithm=HASH_ALGORITHM,
                        canonicalisation=DOCUMENT_CANONICALISATION,
                        content_hash=database.content_hash(),
                        content=database.document(),
                    )
                )
        return out

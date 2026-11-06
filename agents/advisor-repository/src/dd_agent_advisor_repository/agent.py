"""The repository advisor: retrieve → assess → rank → explain, over re3data and FAIRsharing.

It serves four steps of Phase 3 (Figure 3): recommending a repository (R1), whether it assigns
persistent identifiers (R7), its access options and costs, and its certification. Whether a
repository is mandated is a policy question, answered by `advisor.policy` from policy records
(its `PolicyChecks.mandated_repositories`); the orchestrator passes the answer in as
`RepositoryNeeds.mandated`. With mandated repositories the agent describes them, flagging the
needs they do not meet; with none it shortlists. The researcher chooses (TODO(#199)).

Grounding invariant: retrieval precedes any model call, and the model never determines which
repositories are offered or any judgement about them. A candidate names its records once, in
`grounded_on`; what the reader is shown about them is the evidence items' `content`, which the
linter re-hashes (E1, docs/specs/grounding.md).
"""

from __future__ import annotations

from datetime import UTC, datetime

from dd_agent_advisor_repository import assess, rank
from dd_agent_advisor_repository.classes import (
    CandidateBasis,
    RepositoryCandidate,
    RepositoryNeeds,
    RepositoryOptions,
    SearchedSummary,
)
from dd_agent_advisor_repository.explain import Explainer, Item, TemplateExplainer
from dd_agent_advisor_repository.records import DatabaseRecord, Re3dataRecord
from dd_agent_advisor_repository.retrieve import (
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


def _ambiguous(got: _Retrieved) -> str:
    """A sentence for each mandated name that several re3data records bear, or nothing."""
    return "".join(
        f" {name!r} names several re3data records ({', '.join(ids)}); give the identifier."
        for name, ids in got.ambiguous.items()
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
        # Each mandated name that several records bear, with their identifiers.
        self.ambiguous: dict[str, list[str]] = {}

    def summary(self) -> str:
        refs = [self.re3data_ref.as_string()]
        refs += sorted({ref.as_string() for _, ref in self.databases.values()})
        return "; ".join(refs)


class RepositoryAgent:
    spec = AgentSpec(
        agent_id="advisor.repository",
        title="Repository Librarian",
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
            "candidates.ranked_by": Derived(Derivation.TEMPLATE),
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
        databases_fallback: Databases | None = None,
    ) -> None:
        self.repositories = repositories
        self.databases = databases
        self.databases_fallback = databases_fallback
        self.explainer = explainer or TemplateExplainer()

    # --- retrieval ------------------------------------------------------------------------

    def _from_re3data(
        self, needs: RepositoryNeeds, source: Repositories, got: _Retrieved
    ) -> tuple[list[Re3dataRecord], list[str], rank.Matches, dict[str, Re3dataRecord]]:
        """Mandated records and the names not found, or the shortlist's hits and the generalist
        repositories. A name that several records bear is not found, and noted in `got`: the
        researcher is asked for the identifier rather than given a guess."""
        mandated: list[Re3dataRecord] = []
        not_found: list[str] = []
        matches = rank.Matches()
        hits: dict[str, Re3dataRecord] = {}
        for ref in needs.mandated:
            if ref.re3data_id:
                by_id = source.fetch(ref.re3data_id)
                named = [by_id] if by_id is not None else []
            else:
                named = source.find(ref.name)
            if len(named) != 1:
                not_found.append(ref.name)
                if named:
                    got.ambiguous[ref.name] = [n.re3data_id for n in named]
                continue
            if named[0].re3data_id not in {m.re3data_id for m in mandated}:
                mandated.append(named[0])
        if not needs.mandated:
            for query in rank.queries(needs):
                found = source.search(query)
                for hit in found:
                    hits.setdefault(hit.record.re3data_id, hit.record)
                    matches.add(query, hit.record.re3data_id)
            for rid in rank.generalists():
                if rid not in hits and (record := source.fetch(rid)) is not None:
                    hits[rid] = record
        return mandated, not_found, matches, hits

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
        try:
            got = _Retrieved(source.snapshot_ref())
            mandated, not_found, matches, hits = self._from_re3data(needs, source, got)
        except RegistryUnavailable as exc:
            return _abstain(
                ReasonCode.REGISTRY_UNAVAILABLE,
                f"re3data could not be read: {exc}. This is not an empty result.",
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
                    f"({got.summary()}).{_ambiguous(got)} Check the names, or give the re3data "
                    "identifiers. " + source.credit(),
                )
            chosen = [(r, CandidateBasis.MANDATED, None, ()) for r in mandated]
        else:
            if not hits:
                return _abstain(
                    ReasonCode.NO_CANDIDATES_RETRIEVED,
                    f"re3data ({got.summary()}) returned nothing for: "
                    + "; ".join(queries)
                    + ". "
                    + source.credit(),
                )
            ranked = rank.rank(matches, hits, needs)
            if not ranked:
                return _abstain(
                    ReasonCode.NO_QUALIFYING_RESOURCE,
                    f"{len(hits)} repositories were retrieved ({got.summary()}) but none "
                    f"reached the floor of {rank.config()['confidence_floor']} or accepts "
                    "deposits. Searched: " + "; ".join(queries) + ". " + source.credit(),
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
        for item, (_, _, score, reasons), rationale in zip(
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
                    ranked_by=list(reasons),
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
            statement += f" No record found for: {', '.join(not_found)}.{_ambiguous(got)}"
        themes = [q.text for q in rank.queries(needs) if q.label == rank.THEME]
        chosen_ids = {record.re3data_id for record, *_ in chosen}
        disciplinary = set(matches.themes) - set(rank.generalists())
        if not needs.mandated and themes and not chosen_ids & disciplinary:
            statement += (
                " No discipline-specific repository matched the themes ("
                + "; ".join(themes)
                + "), so only generalist and institutional repositories are offered. The broad "
                "field of study, such as environmental science, may find repositories of the "
                "discipline that a narrow topic does not."
            )
        if not needs.mandated:
            statement += (
                " No mandated repository was given; a funder, journal or institution may still "
                "require one, so check their policies before choosing from this shortlist."
            )
        statement += " The researcher chooses; human review is required. " + source.credit()
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
            model_calls=explanation.calls.calls if explanation.calls else (),
            prompts=explanation.calls.prompts if explanation.calls else {},
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

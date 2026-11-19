"""The repository advisor: retrieve → assess → rank → explain, over re3data and FAIRsharing.

It serves four steps of Phase 3 (Figure 3): recommending a repository (R1), whether it assigns
persistent identifiers (R7), its access options and costs, and its certification. Whether a
repository is mandated is a policy question, answered by `advisor.policy` from policy records
(its `PolicyChecks.mandated_repositories`); the orchestrator passes the answer in as
`RepositoryNeeds.mandated`. With mandated repositories the agent describes them, flagging the
needs they do not meet; with none it shortlists. A repository the researcher only names or asks
about (`RepositoryNeeds.asked_about`) is not a mandate: it is described alongside the shortlist,
never instead of it, and never marked mandated (#1167). The researcher chooses (TODO(#199)). In a
project, decided required repositories are mandated too, and the repository the researcher chose
is described when nothing else is asked, and a repository a confirmed sharing commitment of the
data management plan names is described beside the shortlist, not mandated (`given.py`, #1233).

Grounding invariant: retrieval precedes any model call, and the model never determines which
repositories are offered or any judgement about them. A candidate names its records once, in
`grounded_on`; what the reader is shown about them is the evidence items' `content`, which the
linter re-hashes (E1, docs/specs/grounding.md).
"""

from __future__ import annotations

from datetime import UTC, datetime

from dd_agent_advisor_repository import aliases, assess, choose, given, rank
from dd_agent_advisor_repository.classes import (
    RepositoryCandidate,
    RepositoryNeeds,
    RepositoryOptions,
    RepositoryRef,
    SearchedSummary,
)
from dd_agent_advisor_repository.explain import Explainer, Item, Rationale, TemplateExplainer
from dd_agent_advisor_repository.records import DatabaseRecord, Re3dataRecord
from dd_agent_advisor_repository.retrieve import Databases, Repositories
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
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, HASH_ALGORITHM
from dd_sdk.registry import RegistryUnavailable, SnapshotRef
from dd_sdk.tracing import retrieval_span


class _Retrieved:
    """The records one run retrieved, and which copy of each registry answered."""

    def __init__(self, re3data_ref: SnapshotRef) -> None:
        self.re3data_ref = re3data_ref
        self.repositories: dict[str, Re3dataRecord] = {}
        # Each FAIRsharing record with the copy that answered for it: the live route may fail
        # part-way through a run, after which the snapshot answers.
        self.databases: dict[str, tuple[DatabaseRecord, SnapshotRef]] = {}
        self.databases_down = False
        # Each name given (mandated or asked about) that several records bear, with their
        # identifiers.
        self.ambiguous: dict[str, list[str]] = {}
        # Each name given that re3data does not list, read through `aliases.yaml`, with the
        # identifier of the record it led to.
        self.aliased: dict[str, str] = {}

    def summary(self) -> str:
        refs = [self.re3data_ref.as_string()]
        refs += sorted({ref.as_string() for _, ref in self.databases.values()})
        return "; ".join(refs)


def _lookup(
    refs: list[RepositoryRef], source: Repositories, got: _Retrieved, named: choose.Named
) -> list[Re3dataRecord]:
    """The records of the repositories `refs` names, each once; the names not found go to
    `named.not_found` (`_from_re3data`)."""
    records: list[Re3dataRecord] = []
    for ref in refs:
        if ref.re3data_id:
            by_id = source.fetch(ref.re3data_id)
            found = [by_id] if by_id is not None else []
        else:
            found = source.find(ref.name)
            if not found and (alias := aliases.re3data_id(ref.name)) is not None:
                by_alias = source.fetch(alias)
                found = [by_alias] if by_alias is not None else []
                if found:
                    got.aliased[ref.name] = alias
        if len(found) != 1:
            named.not_found.append(ref.name)
            if found:
                got.ambiguous[ref.name] = [n.re3data_id for n in found]
            continue
        if found[0].re3data_id not in {r.re3data_id for r in records}:
            records.append(found[0])
    return records


def _shortlist(
    needs: RepositoryNeeds, source: Repositories
) -> tuple[rank.Matches, dict[str, Re3dataRecord]]:
    """The shortlist's hits, by text and by the themes' DFG subjects, and the generalist
    repositories (`_from_re3data`)."""
    matches = rank.Matches()
    hits: dict[str, Re3dataRecord] = {}
    limit = int(rank.config()["search_limit"])
    themes = [q.text for q in rank.queries(needs) if q.label == rank.THEME]
    if themes:
        rank.resolve(themes, source.subjects(), matches)
    for query in rank.queries(needs):
        found = source.search(query)
        matches.add(query, found)
        for hit in found[:limit]:
            hits.setdefault(hit.record.re3data_id, hit.record)
    for theme in themes:
        filed = [r for c in matches.subjects[theme] for r in source.with_subject(c)]
        for found_record in rank.by_subject(theme, filed, matches):
            hits.setdefault(found_record.re3data_id, found_record)
    for rid in rank.generalists():
        if rid not in hits and (record := source.fetch(rid)) is not None:
            hits[rid] = record
    return matches, hits


def _items(chosen: list[choose.Chosen], got: _Retrieved, needs: RepositoryNeeds) -> list[Item]:
    """What the explainer is told about each candidate chosen."""
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
    return items


def _candidate(
    item: Item, score: float | None, reasons: tuple[str, ...], rationale: Rationale
) -> RepositoryCandidate:
    grounded = [
        GroundingRef(source_id=item.record.re3data_id, content_hash=item.record.content_hash())
    ]
    if item.database is not None:
        grounded.append(
            GroundingRef(
                source_id=item.database.fairsharing_id,
                content_hash=item.database.content_hash(),
            )
        )
    return RepositoryCandidate(
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


class RepositoryAgent:
    spec = AgentSpec(
        agent_id="advisor.repository",
        title="Repository Librarian",
        icon="🏛️",
        version="0.1.0-alpha",
        description=(
            "Recommends data repositories from re3data, or describes the ones mandated, with "
            "their persistent identifiers, access, costs and certification as the registries "
            "record them. Repositories the researcher asks about are described alongside the "
            "shortlist; only a policy's requirement is mandated. The researcher chooses."
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
        self, project: given.Given, source: Repositories, got: _Retrieved
    ) -> tuple[choose.Named, rank.Matches, dict[str, Re3dataRecord]]:
        """The records of the repositories named, mandated or asked about, and the shortlist's
        hits (by text and by the themes' DFG subjects) with the generalist repositories. A
        mandated repository replaces the shortlist; one the researcher asked about does not, and
        a repository both mandated and asked about is mandated. One a confirmed plan commitment
        names is described like one asked about, and one both is described as the plan's. With
        no theme, kind of data or affiliation there is nothing to shortlist on. A name that
        several records bear is not found, and noted in `got`: the researcher is asked for the
        identifier rather than given a guess."""
        needs = project.needs
        named = choose.Named()
        named.mandated = _lookup(needs.mandated, source, got, named)
        mandated_ids = {r.re3data_id for r in named.mandated}
        named.in_plan = [
            r
            for r in _lookup(project.in_plan, source, got, named)
            if r.re3data_id not in mandated_ids
        ]
        described = mandated_ids | {r.re3data_id for r in named.in_plan}
        named.asked_about = [
            r
            for r in _lookup(needs.asked_about, source, got, named)
            if r.re3data_id not in described
        ]
        if needs.mandated or not rank.queries(needs):
            return named, rank.Matches(), {}
        matches, hits = _shortlist(needs, source)
        return named, matches, hits

    def _collect(self, records: list[Re3dataRecord], got: _Retrieved, ctx: RunContext) -> None:
        """Keep the records retrieved, fetch the FAIRsharing records they cross-reference, and
        open one retrieval span per record: this is the evidence the linter matches on."""
        for record in records:
            got.repositories[record.re3data_id] = record
        for record in got.repositories.values():
            if record.fairsharing_id and record.fairsharing_id not in got.databases:
                self._database(record.fairsharing_id, got)
        for rid, repository in got.repositories.items():
            with retrieval_span(ctx.tracer, rid, repository.content_hash()):
                pass
        # A FAIRsharing record by its own identifier, as the candidate cites it, not as re3data
        # wrote it (#741).
        for database, _ in got.databases.values():
            with retrieval_span(ctx.tracer, database.fairsharing_id, database.content_hash()):
                pass

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
        assert isinstance(request.input, RepositoryNeeds)  # the conductor checked spec.accepts
        # What people in the project decided takes precedence over what the caller wrote.
        project = given.with_project(request.input)
        needs = project.needs
        if not (needs.mandated or project.in_plan or needs.asked_about or rank.queries(needs)):
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "The needs name no repository, no theme or kind of data, and no affiliation, so "
                "there was nothing to look up.",
            )

        source = self.repositories
        try:
            got = _Retrieved(source.snapshot_ref())
            named, matches, hits = self._from_re3data(project, source, got)
        except RegistryUnavailable as exc:
            return abstain(
                ReasonCode.REGISTRY_UNAVAILABLE,
                f"re3data could not be read: {exc}. This is not an empty result.",
            )
        self._collect(
            [*named.mandated, *named.in_plan, *named.asked_about, *hits.values()], got, ctx
        )

        # The shortlist's queries; none when a mandate replaces the shortlist.
        shortlisted = [] if needs.mandated else [q.describe() for q in rank.queries(needs)]
        searched = SearchedSummary(
            queries=[f"mandated: {r.name!r}" for r in needs.mandated]
            + [f"in the data management plan: {r.name!r}" for r in project.in_plan]
            + [f"asked about: {r.name!r}" for r in needs.asked_about]
            + shortlisted,
            snapshot_ref=got.summary(),
            candidates_retrieved=len(got.repositories),
        )

        ranked = rank.rank(matches, hits, needs) if hits else []
        chosen = choose.choose(named, ranked, project.only_chosen)
        if not chosen:
            return choose.abstention(named, got, len(hits), shortlisted, source)
        searched = searched.model_copy(update={"candidates_qualifying": len(chosen)})

        items = _items(chosen, got, needs)
        # Explain — after retrieval, over decided candidates only.
        explanation = self.explainer.explain(needs, items, ctx)

        candidates = [
            _candidate(item, score, reasons, rationale)
            for item, (_, _, score, reasons), rationale in zip(
                items, chosen, explanation.rationales, strict=True
            )
        ]

        evidence = self._evidence(candidates, got)
        grounded_on = [
            GroundingRef(source_id=e.source_id, content_hash=e.content_hash) for e in evidence
        ]
        statement = choose.statement(
            needs, candidates, len(evidence), got, named, ranked, shortlisted
        )
        statement += " The researcher chooses; human review is required. " + source.credit()
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
            payload=RepositoryOptions(
                candidates=candidates,
                not_found=named.not_found,
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
        # Keyed by the record's own identifier, which the candidate grounds on: re3data may cite
        # it in another case (FAIRsharing.d6pe1f for FAIRsharing.d6Pe1f, #741).
        for _, (database, ref) in sorted(got.databases.items()):
            if database.fairsharing_id in cited - {e.source_id for e in out}:
                out.append(
                    EvidenceItem(
                        source_id=database.fairsharing_id,
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

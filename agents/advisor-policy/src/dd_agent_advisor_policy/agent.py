"""The policy advisor: retrieve → match → assess → explain, over FAIRsharing's policy records.

It serves the first step of Phase 2 (Figure 2), checking funder, journal and institutional data
sharing policies, and the first step of Phase 3 (Figure 3), whether the funder, journal or
institution mandates a repository. The repositories a policy requires are returned in the form
`advisor.repository` takes as `RepositoryNeeds.mandated`.

Grounding invariant: retrieval precedes any model call, and the model never determines which
policies are matched or what any obligation is. A matched policy names its record once, in
`grounded_on`; what the reader is shown about it is the evidence item's `content`, which the linter
re-hashes (E1, docs/specs/grounding.md). Where policies differ, the agent flags it for human review
and never decides which applies.

Before FAIRsharing is searched, each funder is identified in ROR (`resolve.py`): a name that ROR
gives to one organisation is searched by every name ROR records for it, and the funder's ROR record
is cited, so its identifier can be passed on. A name ROR gives to more than one organisation is not
guessed: the candidates are returned, each grounded on its ROR record, and the researcher is asked
which they mean. ROR's records are evidence like FAIRsharing's, under the same canonicalisation.

Each journal is likewise identified in Crossref (`journals.py`), by its ISSN or exact title, so
that its publisher's own policy is searched for as well as the journal's; a title that Crossref
gives to journals of different publishers is asked about. The `journals` setting, which a
deployment's profile may turn `off`, decides whether Crossref is asked
(docs/specs/policy-and-identity.md).
"""

from __future__ import annotations

from datetime import UTC, datetime

from dd_agent_advisor_policy import assess, match
from dd_agent_advisor_policy.classes import (
    Actor,
    ActorRole,
    AmbiguousActor,
    MatchedPolicy,
    PolicyChecks,
    PolicyConflict,
    PolicyContext,
    RepositoryRef,
    ResolvedFunder,
    ResolvedJournal,
    SearchedSummary,
)
from dd_agent_advisor_policy.explain import Explainer, Item, TemplateExplainer
from dd_agent_advisor_policy.journals import Journal, Journals
from dd_agent_advisor_policy.records import PolicyRecord
from dd_agent_advisor_policy.resolve import (
    Ambiguous,
    JournalAmbiguous,
    JournalFound,
    Resolution,
    Resolved,
    Unknown,
    names,
    publishers,
    resolve,
    resolve_journal,
)
from dd_agent_advisor_policy.retrieve import Policies, RegistryUnavailable, SnapshotRef
from dd_agent_advisor_policy.ror import Organisation, Organisations
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext, Setting, setting
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
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, HASH_ALGORITHM, content_hash
from dd_sdk.tracing import retrieval_span


def _abstain(reason: ReasonCode, statement: str) -> AgentResult:
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.ABSTAINED, reason_code=reason, statement=statement)
    )


def _ref(record: PolicyRecord) -> GroundingRef:
    return GroundingRef(source_id=record.fairsharing_id, content_hash=record.content_hash())


# A record from ROR or Crossref that identifies an actor: cited by its id and the hash of its
# document, under the same canonicalisation as a policy record.
Identity = Organisation | Journal

# The setting that decides whether journals are identified in Crossref.
JOURNALS = "journals"
CROSSREF, OFF = "crossref", "off"


def organisation_hash(org: Identity) -> str:
    return content_hash(org.document(), DOCUMENT_CANONICALISATION)


def _org_ref(org: Identity) -> GroundingRef:
    return GroundingRef(source_id=org.id, content_hash=organisation_hash(org))


def _matched(
    searched: list[tuple[Actor, list[str], list[str]]], source: Policies
) -> list[tuple[Actor, list[PolicyRecord]]]:
    return [
        (actor, match.match(actor, source, wanted, publisher))
        for actor, wanted, publisher in searched
    ]


def _candidate(org: Identity) -> str:
    if isinstance(org, Journal):
        by = f", published by {org.publisher}" if org.publisher else ""
        return f"{org.title} (ISSN {', '.join(org.issns)}{by})"
    where = f", {', '.join(org.country_codes)}" if org.country_codes else ""
    return f"{org.label} ({org.id}{where})"


def _ambiguity(actor: Actor, candidates: tuple[Identity, ...]) -> str:
    if candidates and isinstance(candidates[0], Journal):
        return (
            f"{actor.name!r} is the title of {len(candidates)} journals in Crossref with different "
            "publishers: "
            + "; ".join(_candidate(o) for o in candidates)
            + ". Say which, by giving its ISSN, and its policy will be looked up."
        )
    return (
        f"{actor.name!r} could be any of {len(candidates)} organisations in ROR: "
        + "; ".join(_candidate(o) for o in candidates)
        + ". Say which, by giving its ROR identifier, and its policy will be looked up."
    )


class PolicyAgent:
    spec = AgentSpec(
        agent_id="advisor.policy",
        title="Policy Adviser",
        version="0.1.0-alpha",
        description=(
            "Checks what the data policies of a project's funders, journals and institution ask "
            "of its data, as FAIRsharing's policy records state it, and flags where they differ. "
            "A person decides which applies."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(PolicyContext),),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload=ClassSchema.of(PolicyChecks),
        derivations={
            "policies.obligations.strength": Derived(Derivation.REGISTRY),
            "policies.obligations.recorded_as": Derived(Derivation.REGISTRY),
            "policies.notes": Derived(Derivation.TEMPLATE),
            "policies.rationale": Derived(Derivation.MODEL, recorded_in="rationale_derivation"),
            "conflicts.description": Derived(Derivation.TEMPLATE),
            "mandated_repositories.name": Derived(Derivation.REGISTRY),
            "funders.crossref_funder_id": Derived(Derivation.REGISTRY),
            "journals.issn": Derived(Derivation.REGISTRY),
        },
        serves=("governance.policies", "repository.mandated"),
        settings={
            JOURNALS: Setting(
                (CROSSREF, OFF),
                CROSSREF,
                "Identify each journal in Crossref's public API, by ISSN or exact title, so that "
                "its publisher's policy is found too. Off: journals are matched by the name "
                "given only.",
            ),
        },
    )

    def __init__(
        self,
        policies: Policies,
        explainer: Explainer | None = None,
        fallback: Policies | None = None,
        organisations: Organisations | None = None,
        organisations_fallback: Organisations | None = None,
        journals: Journals | None = None,
    ) -> None:
        self.policies = policies
        self.fallback = fallback
        self.explainer = explainer or TemplateExplainer()
        self.organisations = organisations
        self.organisations_fallback = organisations_fallback
        self.journals = journals

    def _resolve_journals(
        self, actors: list[Actor], resolutions: list[Resolution], ctx: RunContext
    ) -> tuple[list[Resolution], str | None, str | None]:
        """Each journal identified in Crossref, which copy answered, and why Crossref was not
        consulted, when it was meant to be and was not. As with ROR, Crossref being unavailable
        does not stop the run: journals are then searched by the name given."""
        if not any(a.role == ActorRole.JOURNAL for a in actors):
            return resolutions, None, None
        if setting(ctx, self.spec, JOURNALS) == OFF:
            return resolutions, None, None
        if self.journals is None:
            return resolutions, None, "no Crossref client is configured"
        try:
            ref = self.journals.snapshot_ref()
            found = [
                resolve_journal(a, self.journals) if a.role == ActorRole.JOURNAL else r
                for a, r in zip(actors, resolutions, strict=True)
            ]
        except RegistryUnavailable as exc:
            return resolutions, None, str(exc)
        return found, ref.as_string(), None

    def _resolve(self, actors: list[Actor]) -> tuple[list[Resolution], str | None, str | None]:
        """Each actor's resolution in ROR, which copy of ROR answered, and why ROR was not
        consulted, when it was not. ROR being unavailable does not stop the run: funders are
        then searched by the name given, as they were before, and the statement says so."""
        unknown: list[Resolution] = [Unknown() for _ in actors]
        if not any(a.role == ActorRole.FUNDER for a in actors):
            return unknown, None, None
        if self.organisations is None:
            return unknown, None, "no copy of ROR is configured"
        try:
            ref = self.organisations.snapshot_ref()
            return [resolve(a, self.organisations) for a in actors], ref.as_string(), None
        except RegistryUnavailable as exc:
            if self.organisations_fallback is None:
                return unknown, None, str(exc)
            try:
                found = [resolve(a, self.organisations_fallback) for a in actors]
            except RegistryUnavailable as again:
                return unknown, None, f"{exc}; {again}"
            stale = SnapshotRef(label=self.organisations_fallback.snapshot_ref().label, stale=True)
            return found, stale.as_string(), None

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        context = request.input
        assert isinstance(context, PolicyContext)  # the conductor checked spec.accepts
        if not context.actors:
            return _abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "The context names no funder, journal or institution, so there was no policy "
                "to look up.",
            )

        resolutions, ror_where, ror_unavailable = self._resolve(context.actors)
        resolutions, crossref_where, crossref_unavailable = self._resolve_journals(
            context.actors, resolutions, ctx
        )
        ambiguous: list[tuple[Actor, tuple[Identity, ...]]] = [
            (actor, r.candidates)
            for actor, r in zip(context.actors, resolutions, strict=True)
            if isinstance(r, Ambiguous | JournalAmbiguous)
        ]
        found_journals = [
            (actor, r)
            for actor, r in zip(context.actors, resolutions, strict=True)
            if isinstance(r, JournalFound)
        ]
        resolved = [
            (actor, r.organisation)
            for actor, r in zip(context.actors, resolutions, strict=True)
            if isinstance(r, Resolved)
        ]
        # An ambiguous funder is not searched: its policy is looked up once the researcher says
        # which organisation they mean.
        searched = [
            (actor, names(actor, r), publishers(r))
            for actor, r in zip(context.actors, resolutions, strict=True)
            if not isinstance(r, Ambiguous | JournalAmbiguous)
        ]

        snapshot_ref = self.policies.snapshot_ref()
        try:
            matched = _matched(searched, self.policies)
        except RegistryUnavailable as exc:
            if self.fallback is None:
                return _abstain(
                    ReasonCode.REGISTRY_UNAVAILABLE,
                    f"FAIRsharing could not be searched: {exc}. This is not an empty result.",
                )
            try:
                matched = _matched(searched, self.fallback)
            except RegistryUnavailable as again:
                return _abstain(
                    ReasonCode.REGISTRY_UNAVAILABLE,
                    f"FAIRsharing could not be searched ({exc}), nor its snapshot ({again}).",
                )
            snapshot_ref = SnapshotRef(
                label=self.fallback.snapshot_ref().label,
                stale=True,
                notes=[f"live route failed: {exc}"],
            )
        where = snapshot_ref.as_string()

        records: dict[str, PolicyRecord] = {}
        for _, found in matched:
            for record in found:
                records.setdefault(record.fairsharing_id, record)
        organisations: dict[str, Identity] = {org.id: org for _, org in resolved}
        for _, candidates in ambiguous:
            for org in candidates:
                if isinstance(org, Organisation):
                    organisations.setdefault(org.id, org)
        journals: dict[str, Identity] = {
            j.id: j for _, found in found_journals for j in found.journals
        }
        for _, candidates in ambiguous:
            for org in candidates:
                if isinstance(org, Journal):
                    journals.setdefault(org.id, org)
        # One retrieval span per record: this is the evidence the linter matches on.
        for fid, record in records.items():
            with retrieval_span(ctx.tracer, fid, record.content_hash()):
                pass
        for oid, org in (organisations | journals).items():
            with retrieval_span(ctx.tracer, oid, organisation_hash(org)):
                pass

        queries = [
            f"{actor.role.value}: {actor.fairsharing_id or repr(name)}"
            for actor, wanted, publisher in searched
            for name in ([actor.fairsharing_id] if actor.fairsharing_id else wanted + publisher)
        ]
        queries += [
            f"ror: {actor.ror_id or repr(actor.name)}"
            if actor.role == ActorRole.FUNDER
            else f"crossref: {actor.issn or repr(actor.name)}"
            for actor, _ in ambiguous
        ]
        queries += [f"ror: {actor.ror_id or repr(actor.name)}" for actor, _ in resolved]
        queries += [f"crossref: {actor.issn or repr(actor.name)}" for actor, _ in found_journals]
        no_record = [actor.name for actor, found in matched if not found]
        ror_note = (
            f" ROR was not consulted ({ror_unavailable}); funders were searched by the name given."
            if ror_unavailable
            else ""
        )
        if crossref_unavailable:
            ror_note += (
                f" Crossref was not consulted ({crossref_unavailable}); journals were searched by "
                "the name given, so a publisher's policy may have been missed."
            )
        questions = " ".join(_ambiguity(actor, candidates) for actor, candidates in ambiguous)
        funders = [
            ResolvedFunder(
                actor=actor.name,
                crossref_funder_id=org.crossref_funder_preferred,
                grounded_on=[_org_ref(org)],
            )
            for actor, org in resolved
        ]
        unresolved = [
            AmbiguousActor(
                actor=actor.name,
                role=actor.role,
                grounded_on=[_org_ref(o) for o in candidates],
            )
            for actor, candidates in ambiguous
        ]
        resolved_journals = [
            ResolvedJournal(
                actor=actor.name,
                issn=actor.issn or found.journals[0].issns[0],
                grounded_on=[_org_ref(j) for j in found.journals],
            )
            for actor, found in found_journals
        ]
        org_refs = [_org_ref(o) for _, o in sorted((organisations | journals).items())]
        searched_summary = SearchedSummary(
            queries=queries,
            snapshot_ref="; ".join(w for w in (where, ror_where, crossref_where) if w),
            policies_retrieved=len(records),
        )
        identified = (
            " Funders identified in ROR: "
            + "; ".join(f"{actor.name!r} as {_candidate(org)}" for actor, org in resolved)
            + f" ({ror_where})."
            if resolved
            else ""
        )
        if found_journals:
            identified += (
                " Journals identified in Crossref: "
                + "; ".join(
                    f"{actor.name!r} as {_candidate(found.journals[0])}"
                    for actor, found in found_journals
                )
                + f" ({crossref_where}); each publisher's own policy was searched for too."
            )
        if not records and not organisations and not journals:
            return _abstain(
                ReasonCode.NO_CANDIDATES_RETRIEVED,
                f"FAIRsharing ({where}) has no policy record for {', '.join(no_record)}. "
                "Many institutions have none; check the policies directly, including whether "
                "they require a particular repository." + ror_note,
            )
        # No policy, but ROR identified a funder or found candidates for one: the payload carries
        # them, grounded on their ROR records, so the identifier can be passed on or chosen.
        if not records:
            statement = "No policy record was matched." + identified
            if questions:
                statement += " " + questions
            if no_record:
                statement += (
                    f" FAIRsharing ({where}) has no policy record for {', '.join(no_record)}; "
                    "check their policies directly, including whether they require a particular "
                    "repository."
                )
            statement += ror_note + " Human review is required."
            return AgentResult(
                outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
                payload=PolicyChecks(
                    no_record=no_record,
                    funders=funders,
                    journals=resolved_journals,
                    ambiguous=unresolved,
                    searched=searched_summary,
                    grounded_on=org_refs,
                ),
                evidence=self._org_evidence(organisations, ror_where or "")
                + self._org_evidence(journals, crossref_where or ""),
            )

        items = [
            Item(
                record=record,
                actor=actor,
                obligations=tuple(assess.obligations(record)),
                notes=tuple(assess.notes(record, context)),
            )
            for actor, found in matched
            for record in found
        ]
        # Explain — after retrieval, over assessed policies only.
        explanation = self.explainer.explain(context, items, ctx)
        policies = [
            MatchedPolicy(
                actor=item.actor.name,
                role=item.actor.role,
                obligations=list(item.obligations),
                notes=list(item.notes),
                rationale=rationale.text,
                rationale_derivation=rationale.derivation,
                grounded_on=[_ref(item.record)],
            )
            for item, rationale in zip(items, explanation.rationales, strict=True)
        ]

        conflicts = [
            PolicyConflict(
                kind=kind,
                description=description,
                grounded_on=[_ref(r) for r in involved],
            )
            for kind, involved, description in assess.conflicts(
                [assess.Stated(r, assess.obligations(r)) for r in records.values()]
            )
        ]
        mandated: dict[str, RepositoryRef] = {}
        for record in records.values():
            for ref in assess.mandated(record):
                mandated.setdefault(ref.name.casefold(), ref)

        evidence = self._evidence(records, where)
        statement = (
            f"Policies matched: {len(policies)} for "
            f"{len(searched) - len(no_record)} of {len(context.actors)} actor(s), "
            f"grounded in {len(evidence)} FAIRsharing record(s) ({where})."
        )
        statement += identified
        if questions:
            statement += " " + questions
        if conflicts:
            statement += (
                f" Obligations the policies state differently: {len(conflicts)}; a person "
                "should decide which applies."
            )
        if mandated:
            statement += " Repositories required: " + ", ".join(r.name for r in mandated.values())
            statement += "."
        else:
            statement += (
                " No matched record names a required repository. FAIRsharing's policy records do "
                "not say which repositories a policy requires, so this is not evidence that none "
                "is required: check each policy's own text before choosing a repository."
            )
        if no_record:
            statement += (
                f" No policy record for: {', '.join(no_record)}; what they require, including "
                "any required repository, was not checked."
            )
        statement += ror_note + " Human review is required."
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
            payload=PolicyChecks(
                policies=policies,
                conflicts=conflicts,
                mandated_repositories=list(mandated.values()),
                no_record=no_record,
                funders=funders,
                journals=resolved_journals,
                ambiguous=unresolved,
                searched=searched_summary,
                grounded_on=[_ref(r) for _, r in sorted(records.items())] + org_refs,
            ),
            evidence=evidence
            + self._org_evidence(organisations, ror_where or "")
            + self._org_evidence(journals, crossref_where or ""),
            model_id=self.explainer.model_id,
            input_tokens=explanation.usage.input_tokens,
            output_tokens=explanation.usage.output_tokens,
            model_calls=explanation.calls.calls if explanation.calls else (),
            prompts=explanation.calls.prompts if explanation.calls else {},
        )

    @staticmethod
    def _evidence(records: dict[str, PolicyRecord], snapshot_ref: str) -> list[EvidenceItem]:
        now = datetime.now(UTC)
        return [
            EvidenceItem(
                source_id=fid,
                source_uri=record.source_uri,
                retrieved_at=now,
                snapshot_ref=snapshot_ref,
                hash_algorithm=HASH_ALGORITHM,
                canonicalisation=DOCUMENT_CANONICALISATION,
                content_hash=record.content_hash(),
                content=record.document(),
            )
            for fid, record in sorted(records.items())
        ]

    @staticmethod
    def _org_evidence(organisations: dict[str, Identity], snapshot_ref: str) -> list[EvidenceItem]:
        now = datetime.now(UTC)
        return [
            EvidenceItem(
                source_id=oid,
                source_uri=oid,
                retrieved_at=now,
                snapshot_ref=snapshot_ref,
                hash_algorithm=HASH_ALGORITHM,
                canonicalisation=DOCUMENT_CANONICALISATION,
                content_hash=organisation_hash(org),
                content=org.document(),
            )
            for oid, org in sorted(organisations.items())
        ]

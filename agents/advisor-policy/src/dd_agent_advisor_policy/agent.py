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

Then each policy's own text is read (`policy_text.py`, `extract.py`): the page or PDF each matched
record names, and any `policy_url` the researcher gives. A model reports what the text says of each
kind of obligation, with the passage that says so; the code keeps a reading only if its quote is
in the text. This adds to what the record says and never changes it: the readings sit beside the
record's obligations, both shown, for a person to confirm. The `policy_text` setting decides
whether pages are read; without a model nothing is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from dd_agent_advisor_policy import assess, match
from dd_agent_advisor_policy.classes import (
    Actor,
    ActorRole,
    AmbiguousActor,
    MatchedPolicy,
    ObligationKind,
    PolicyChecks,
    PolicyConflict,
    PolicyContext,
    PolicyReading,
    ReadingStatus,
    RepositoryRef,
    ResolvedFunder,
    ResolvedJournal,
    SearchedSummary,
    Strength,
)
from dd_agent_advisor_policy.explain import Explainer, Explanation, Item, TemplateExplainer
from dd_agent_advisor_policy.extract import Extractor, NoExtractor
from dd_agent_advisor_policy.journals import Journal, Journals
from dd_agent_advisor_policy.policy_text import Pages, PolicyText, UnreadableError, readable_url
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
from dd_sdk.prompts import ModelCallLog
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
# The setting that decides whether each policy's own text is read.
POLICY_TEXT = "policy_text"
READ = "read"


def text_hash(text: PolicyText) -> str:
    return content_hash(text.document(), DOCUMENT_CANONICALISATION)


def _text_ref(text: PolicyText) -> GroundingRef:
    return GroundingRef(source_id=text.url, content_hash=text_hash(text))


@dataclass
class TextReadings:
    """What reading the policies' own text gave: the readings, the evidence and references they
    rest on, the tokens and calls spent, and a sentence for the statement."""

    readings: list[PolicyReading] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    refs: list[GroundingRef] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    calls: ModelCallLog | None = None
    note: str = ""


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


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
            "of its data, as FAIRsharing's policy records state it and as the policies' own text "
            "says, quoting the passage each obligation comes from, and flags where they differ. "
            "A person confirms each and decides which applies."
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
            "readings.status": Derived(Derivation.TEMPLATE),
            "readings.reason": Derived(Derivation.TEMPLATE),
            "readings.dropped": Derived(Derivation.TEMPLATE),
            # The quote is not listed: the code has found it, word for word, in the cited text.
            "readings.stated.kind": Derived(Derivation.MODEL),
            "readings.stated.strength": Derived(Derivation.MODEL),
            "readings.stated.value": Derived(Derivation.MODEL),
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
            POLICY_TEXT: Setting(
                (READ, OFF),
                READ,
                "Fetch each matched policy's own page or PDF, and any the researcher gives, and "
                "have the agent's model report what it requires, quoting the passage each "
                "obligation comes from; the code keeps only quotes it finds in the text. Needs a "
                "model. Off: only FAIRsharing's curated records are read.",
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
        pages: Pages | None = None,
        extractor: Extractor | None = None,
    ) -> None:
        self.policies = policies
        self.fallback = fallback
        self.explainer = explainer or TemplateExplainer()
        self.organisations = organisations
        self.organisations_fallback = organisations_fallback
        self.journals = journals
        self.pages = pages
        self.extractor = extractor or NoExtractor()

    def _read_texts(
        self, matched: list[tuple[Actor, list[PolicyRecord]]], ctx: RunContext
    ) -> TextReadings:
        """Fetch and read each policy's own text: the page each matched record names, and each
        `policy_url` given. Every page is fetched, with its retrieval span, before any model is
        called (docs/specs/grounding.md, G1)."""
        out = TextReadings()
        targets: dict[str, tuple[Actor, PolicyRecord | None]] = {}
        for actor, found in matched:
            for record in found:
                url = readable_url(record.homepage)
                if url:
                    targets.setdefault(url, (actor, record))
        for actor, _ in matched:
            url = readable_url(actor.policy_url)
            if url:
                targets.setdefault(url, (actor, None))
        if not targets:
            return out
        if setting(ctx, self.spec, POLICY_TEXT) == OFF:
            out.note = " The policies' own text was not read: the deployment turns reading off."
            return out
        if self.pages is None or isinstance(self.extractor, NoExtractor):
            out.note = (
                " The policies' own text was not read: no model is configured to read it, so "
                "only FAIRsharing's curated records were."
            )
            return out
        where = self.pages.snapshot_ref().as_string()
        fetched: list[tuple[str, Actor, PolicyRecord | None, PolicyText | None, str | None]] = []
        for url, (actor, source) in targets.items():
            try:
                text = self.pages.fetch(url)
            except RegistryUnavailable as exc:
                fetched.append((url, actor, source, None, f"it could not be fetched: {exc}"))
                continue
            except UnreadableError as exc:
                fetched.append((url, actor, source, None, f"unreadable: {exc}"))
                continue
            with retrieval_span(ctx.tracer, url, text_hash(text)):
                pass
            fetched.append((url, actor, source, text, None))
        unread: list[str] = []
        now = datetime.now(UTC)
        for url, actor, origin, page, problem in fetched:
            record_refs = [_ref(origin)] if origin is not None else []
            if page is None:
                if not record_refs:
                    unread.append(f"{url} ({problem})")
                    continue
                out.readings.append(
                    PolicyReading(
                        actor=actor.name,
                        role=actor.role,
                        status=(
                            ReadingStatus.UNREADABLE
                            if (problem or "").startswith("unreadable")
                            else ReadingStatus.NOT_READ
                        ),
                        reason=f"The policy's page {url}: {problem}.",
                        grounded_on=record_refs,
                    )
                )
                continue
            reading = self.extractor.extract(actor, page, ctx, out.calls)
            out.calls = reading.calls or out.calls
            out.input_tokens += reading.usage.input_tokens or 0
            out.output_tokens += reading.usage.output_tokens or 0
            ref = _text_ref(page)
            out.refs.append(ref)
            out.evidence.append(
                EvidenceItem(
                    source_id=page.url,
                    source_uri=page.url,
                    retrieved_at=now,
                    snapshot_ref=where,
                    hash_algorithm=HASH_ALGORITHM,
                    canonicalisation=DOCUMENT_CANONICALISATION,
                    content_hash=ref.content_hash,
                    content=page.document(),
                )
            )
            reasons = []
            if reading.why_not:
                reasons.append(f"The text was not read: {reading.why_not}.")
            if page.truncated:
                reasons.append("The text was long and only its first part was read.")
            out.readings.append(
                PolicyReading(
                    actor=actor.name,
                    role=actor.role,
                    status=ReadingStatus.NOT_READ if reading.why_not else ReadingStatus.READ,
                    stated=reading.checked.stated,
                    dropped=reading.checked.dropped,
                    reason=" ".join(reasons) or None,
                    grounded_on=[ref, *record_refs],
                )
            )
        out.note = self._reading_note(out.readings, matched, unread)
        return out

    def _reading_note(
        self,
        readings: list[PolicyReading],
        matched: list[tuple[Actor, list[PolicyRecord]]],
        unread: list[str],
    ) -> str:
        read = [r for r in readings if r.status == ReadingStatus.READ]
        note = ""
        if read:
            stated = sum(len(r.stated) for r in read)
            note += (
                f" The policies' own text was read for {_plural(len(read), 'policy')} by a model "
                f"({self.extractor.model_id}): {_plural(stated, 'obligation')} found, each with "
                "the passage it comes from, which the agent has checked is in the text. A person "
                "should confirm each against the policy."
            )
            required = sorted(
                {
                    o.value
                    for r in read
                    for o in r.stated
                    if o.kind == ObligationKind.REPOSITORY and o.strength == Strength.REQUIRED
                }
            )
            if required:
                note += " Repositories the text says are required: " + "; ".join(required) + "."
            differ = self._differences(read, matched)
            if differ:
                note += (
                    " The text and its FAIRsharing record state these differently: "
                    + "; ".join(differ)
                    + ". Both are shown; a person should decide."
                )
        not_read = [r for r in readings if r.status != ReadingStatus.READ]
        if not_read:
            note += (
                f" The text of {_plural(len(not_read), 'policy')} was not read; each reading "
                "says why."
            )
        if unread:
            note += " A page given for a policy could not be read: " + "; ".join(unread) + "."
        return note

    @staticmethod
    def _differences(
        read: list[PolicyReading], matched: list[tuple[Actor, list[PolicyRecord]]]
    ) -> list[str]:
        records = {r.fairsharing_id: r for _, found in matched for r in found}
        out: list[str] = []
        for reading in read:
            for ref in reading.grounded_on:
                record = records.get(ref.source_id)
                if record is None:
                    continue
                curated = {
                    o.kind: o.strength
                    for o in assess.obligations(record)
                    if o.strength != Strength.UNSTATED
                }
                for kind in sorted({o.kind for o in reading.stated}):
                    strengths = {o.strength for o in reading.stated if o.kind == kind}
                    if kind in curated and curated[kind] not in strengths:
                        out.append(
                            f"{kind.value.replace('_', ' ')} for {reading.actor!r}: the record "
                            f"says {curated[kind].value}, the text "
                            f"{' and '.join(sorted(s.value for s in strengths))}"
                        )
        return out

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
        texts = self._read_texts(matched, ctx)
        if not records and not organisations and not journals and not texts.readings:
            return _abstain(
                ReasonCode.NO_CANDIDATES_RETRIEVED,
                f"FAIRsharing ({where}) has no policy record for {', '.join(no_record)}. "
                "Many institutions have none; check the policies directly, including whether "
                "they require a particular repository." + texts.note + ror_note,
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
            statement += texts.note + ror_note + " Human review is required."
            return AgentResult(
                outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
                payload=PolicyChecks(
                    no_record=no_record,
                    readings=texts.readings,
                    funders=funders,
                    journals=resolved_journals,
                    ambiguous=unresolved,
                    searched=searched_summary,
                    grounded_on=texts.refs + org_refs,
                ),
                evidence=texts.evidence
                + self._org_evidence(organisations, ror_where or "")
                + self._org_evidence(journals, crossref_where or ""),
                **self._model_use(None, texts),
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
        statement += texts.note + ror_note + " Human review is required."
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
            payload=PolicyChecks(
                policies=policies,
                conflicts=conflicts,
                mandated_repositories=list(mandated.values()),
                no_record=no_record,
                readings=texts.readings,
                funders=funders,
                journals=resolved_journals,
                ambiguous=unresolved,
                searched=searched_summary,
                grounded_on=[_ref(r) for _, r in sorted(records.items())] + texts.refs + org_refs,
            ),
            evidence=evidence
            + texts.evidence
            + self._org_evidence(organisations, ror_where or "")
            + self._org_evidence(journals, crossref_where or ""),
            **self._model_use(explanation, texts),
        )

    def _model_use(self, explanation: Explanation | None, texts: TextReadings) -> dict[str, Any]:
        """The models called in this run, their tokens, calls and prompts: the explainer's and
        the extractor's together."""
        logs = [log for log in (explanation.calls if explanation else None, texts.calls) if log]
        if not logs:
            return {}
        explained = explanation.usage if explanation else None

        def total(a: int | None, b: int) -> int | None:
            return None if a is None and not b else (a or 0) + b

        return {
            "model_id": (explanation and explanation.calls and self.explainer.model_id)
            or (texts.calls and self.extractor.model_id)
            or None,
            "input_tokens": total(
                explained.input_tokens if explained else None, texts.input_tokens
            ),
            "output_tokens": total(
                explained.output_tokens if explained else None, texts.output_tokens
            ),
            "model_calls": tuple(c for log in logs for c in log.calls),
            "prompts": {k: v for log in logs for k, v in log.prompts.items()},
        }

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

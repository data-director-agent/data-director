"""The policy advisor: retrieve → match → assess → advise, over FAIRsharing's policy records,
Jisc Open Policy Finder's and Crossref's journals.

It serves the first step of Phase 2 (Figure 2), checking funder, journal and institutional data
sharing policies, and the first step of Phase 3 (Figure 3), whether the funder, journal or
institution mandates a repository. The repositories a policy requires are returned in the form
`advisor.repository` takes as `RepositoryNeeds.mandated`.

Grounding invariant: retrieval precedes any model call, and a model's word is never taken alone.
The first search is fixed rules (`match.py`, `discover.py`); the model advisor then reads what it
found and may search for more, and the agent keeps an obligation it states only with a quote found
in the cited record, a record it adds only if a tool retrieved it in this run and it is a policy
of the actor's kind, and never removes a policy or an obligation the rules found (`advise.py`).
Each value says how it was derived (`match_derivation`, `derivation`). A matched policy names its
record once, in `grounded_on`; what the reader is shown about it is the evidence item's `content`,
which the linter re-hashes (E1, docs/specs/grounding.md). Where policies differ, the agent flags it
for human review and never decides which applies.

A journal is identified by its ISSN or title in Open Policy Finder and Crossref, and its
publisher's name is searched too, since most journals follow their publisher's policy (#905).
Open Policy Finder is read live, with a key; without one it is not searched and the statement
says so.

Before FAIRsharing is searched, each funder is identified in ROR (`resolve.py`): a name that ROR
gives to one organisation is searched by every name ROR records for it, and the funder's ROR record
is cited, so its identifier can be passed on. A name ROR gives to more than one organisation is not
guessed: the candidates are returned, each grounded on its ROR record, and the researcher is asked
which they mean. ROR's records are evidence like FAIRsharing's, under the same canonicalisation.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from dd_agent_advisor_policy import assess, discover, match
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
    PolicyRegistry,
    ReadingStatus,
    RepositoryRef,
    ResolvedFunder,
    ResolvedJournal,
    SearchedSummary,
    Strength,
)
from dd_agent_advisor_policy.crossref import CrossrefJournals
from dd_agent_advisor_policy.explain import (
    Explainer,
    Explanation,
    Item,
    Rationale,
    TemplateExplainer,
)
from dd_agent_advisor_policy.extract import Extractor, NoExtractor
from dd_agent_advisor_policy.opf import OpenPolicyFinder, OpfRecord
from dd_agent_advisor_policy.policy_text import Pages
from dd_agent_advisor_policy.reading import (
    TextReadings,
    fetch_pages,
    reading_targets,
    text_ref,
    unread_reading,
)
from dd_agent_advisor_policy.records import PolicyRecord
from dd_agent_advisor_policy.resolve import Ambiguous, Resolution, Resolved, Unknown, names, resolve
from dd_agent_advisor_policy.retrieve import Policies, SourceRecord
from dd_agent_advisor_policy.ror import Organisations
from dd_agent_advisor_policy.ror_records import Organisation
from dd_agent_advisor_policy.tools import Lookups
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext, Setting, abstain, setting
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
from dd_sdk.registry import RegistryUnavailable, SnapshotRef
from dd_sdk.tracing import retrieval_span

# The setting that decides whether each policy's own text is read.
POLICY_TEXT = "policy_text"
READ, OFF = "read", "off"


def _ref(record: SourceRecord) -> GroundingRef:
    return GroundingRef(source_id=record.source_id, content_hash=record.content_hash())


def organisation_hash(org: Organisation) -> str:
    return content_hash(org.document(), DOCUMENT_CANONICALISATION)


def _org_ref(org: Organisation) -> GroundingRef:
    return GroundingRef(source_id=org.id, content_hash=organisation_hash(org))


def _matched(
    searched: list[tuple[Actor, list[str]]], source: Policies
) -> list[tuple[Actor, list[PolicyRecord]]]:
    return [(actor, match.match(actor, source, wanted)) for actor, wanted in searched]


def _candidate(org: Organisation) -> str:
    where = f", {', '.join(org.country_codes)}" if org.country_codes else ""
    return f"{org.label} ({org.id}{where})"


def _ambiguity(actor: Actor, candidates: tuple[Organisation, ...]) -> str:
    return (
        f"{actor.name!r} could be any of {len(candidates)} organisations in ROR: "
        + "; ".join(_candidate(o) for o in candidates)
        + ". Say which, by giving its ROR identifier, and its policy will be looked up."
    )


def _journal_ambiguity(actor: Actor, candidates: Sequence[SourceRecord]) -> str:
    return (
        f"{actor.name!r} could be any of {len(candidates)} journals: "
        + "; ".join(c.label for c in candidates)
        + ". Say which, by giving its ISSN, and its policy will be looked up."
    )


def _registry(record: SourceRecord) -> PolicyRegistry:
    return (
        PolicyRegistry.FAIRSHARING
        if isinstance(record, PolicyRecord)
        else PolicyRegistry.OPEN_POLICY_FINDER
    )


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


class PolicyAgent:
    spec = AgentSpec(
        agent_id="advisor.policy",
        title="Policy Adviser",
        icon="📜",
        version="0.1.0-alpha",
        description=(
            "Checks what the data and open access policies of a project's funders, journals and "
            "institution ask of it, from FAIRsharing's policy records and Jisc Open Policy "
            "Finder's, with each obligation quoted from its record, and flags where they differ. "
            "A person decides which applies."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(PolicyContext),),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload=ClassSchema.of(PolicyChecks),
        derivations={
            "policies.match_derivation": Derived(Derivation.REGISTRY),
            "policies.obligations.strength": Derived(Derivation.REGISTRY, recorded_in="derivation"),
            "policies.obligations.recorded_as": Derived(Derivation.REGISTRY),
            "policies.obligations.scope": Derived(Derivation.REGISTRY, recorded_in="derivation"),
            "policies.obligations.value": Derived(Derivation.MODEL, recorded_in="derivation"),
            "policies.obligations.quote": Derived(Derivation.MODEL, recorded_in="derivation"),
            "policies.notes": Derived(Derivation.TEMPLATE),
            "policies.rationale": Derived(Derivation.MODEL, recorded_in="rationale_derivation"),
            "conflicts.description": Derived(Derivation.TEMPLATE),
            "mandated_repositories.name": Derived(Derivation.REGISTRY),
            "funders.crossref_funder_id": Derived(Derivation.REGISTRY),
            "journals.publisher": Derived(Derivation.REGISTRY),
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
            POLICY_TEXT: Setting(
                (READ, OFF),
                READ,
                "Fetch each matched policy's own page or PDF, and any the researcher gives, and "
                "have the agent's model report what it requires, quoting the passage each "
                "obligation comes from; the code keeps only quotes it finds in the text. Needs a "
                "model. Off: only the registries' records are read.",
            ),
        },
    )

    def __init__(  # noqa: PLR0913
        self,
        policies: Policies,
        explainer: Explainer | None = None,
        fallback: Policies | None = None,
        organisations: Organisations | None = None,
        organisations_fallback: Organisations | None = None,
        opf: OpenPolicyFinder | None = None,
        crossref: CrossrefJournals | None = None,
        pages: Pages | None = None,
        extractor: Extractor | None = None,
    ) -> None:
        self.policies = policies
        self.fallback = fallback
        self.explainer = explainer or TemplateExplainer()
        self.organisations = organisations
        self.organisations_fallback = organisations_fallback
        self.opf = opf
        self.crossref = crossref
        self.pages = pages
        self.extractor = extractor or NoExtractor()

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

    def _journals(self, actors: list[Actor]) -> dict[int, discover.Journal]:
        """What Open Policy Finder and Crossref say about each journal given by name or ISSN."""
        if self.opf is None and self.crossref is None:
            return {}
        return {
            n: discover.journal(actor, self.opf, self.crossref)
            for n, actor in enumerate(actors)
            if actor.role == ActorRole.JOURNAL and not actor.fairsharing_id
        }

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:  # noqa: C901, PLR0912, PLR0915
        context = request.input
        assert isinstance(context, PolicyContext)  # the conductor checked spec.accepts
        if not context.actors:
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "The context names no funder, journal or institution, so there was no policy "
                "to look up.",
            )
        actors = list(context.actors)

        # --- the first search: fixed rules over each registry --------------------------------
        resolutions, ror_where, ror_unavailable = self._resolve(actors)
        journals = self._journals(actors)
        ambiguous = [
            (actor, r.candidates)
            for actor, r in zip(actors, resolutions, strict=True)
            if isinstance(r, Ambiguous)
        ]
        ambiguous_journals = [
            (actors[n], list(j.candidates)) for n, j in journals.items() if j.candidates
        ]
        resolved = [
            (actor, r.organisation)
            for actor, r in zip(actors, resolutions, strict=True)
            if isinstance(r, Resolved)
        ]
        blocked = {a.name for a, _ in ambiguous} | {a.name for a, _ in ambiguous_journals}
        # An ambiguous funder or journal is not searched: its policy is looked up once the
        # researcher says which they mean. A journal is searched by its publisher's names too.
        searched = [
            (actor, names(actor, r) + (journals[n].publisher_names if n in journals else []))
            for n, (actor, r) in enumerate(zip(actors, resolutions, strict=True))
            if actor.name not in blocked
        ]

        snapshot_ref = self.policies.snapshot_ref()
        try:
            matched = _matched(searched, self.policies)
        except RegistryUnavailable as exc:
            if self.fallback is None:
                return abstain(
                    ReasonCode.REGISTRY_UNAVAILABLE,
                    f"FAIRsharing could not be searched: {exc}. This is not an empty result.",
                )
            try:
                matched = _matched(searched, self.fallback)
            except RegistryUnavailable as again:
                return abstain(
                    ReasonCode.REGISTRY_UNAVAILABLE,
                    f"FAIRsharing could not be searched ({exc}), nor its snapshot ({again}).",
                )
            snapshot_ref = SnapshotRef(
                label=self.fallback.snapshot_ref().label,
                stale=True,
                notes=[f"live route failed: {exc}"],
            )
        where = snapshot_ref.as_string()

        problems: list[str] = []
        queries_extra: list[str] = []
        opf_matched: list[tuple[Actor, list[OpfRecord]]] = []
        by_name = {a.name: n for n, a in enumerate(actors)}
        for actor, wanted in searched:
            n = by_name[actor.name]
            if actor.role == ActorRole.FUNDER and self.opf is not None:
                try:
                    found, asked = discover.funders(actor, wanted, self.opf)
                    queries_extra += asked
                    opf_matched.append((actor, found))
                except RegistryUnavailable as exc:
                    problems.append(str(exc))
            elif n in journals:
                journal = journals[n]
                queries_extra += journal.queries
                problems += journal.problems
                # The journal's own record carries its publishers' policies; a publisher's
                # record stands in only when Open Policy Finder has none for the journal.
                own = [journal.record] if journal.record else journal.publishers
                opf_matched.append((actor, own[: discover.PER_ACTOR]))
        for _, j in journals.items():
            queries_extra += (
                [q for q in j.queries if q not in queries_extra] if j.candidates else []
            )

        # Every record retrieved, which a model may read and the payload may cite.
        records: dict[str, SourceRecord] = {}
        for _, fs in matched:
            for fs_record in fs:
                records.setdefault(fs_record.source_id, fs_record)
        for _, opf_records in opf_matched:
            for opf_record in opf_records:
                records.setdefault(opf_record.source_id, opf_record)
        for journal in journals.values():
            for other in (
                journal.record,
                journal.crossref,
                *journal.publishers,
                *journal.candidates,
            ):
                if other is not None:
                    records.setdefault(other.source_id, other)
        organisations: dict[str, Organisation] = {org.id: org for _, org in resolved}
        for _, candidates in ambiguous:
            for org in candidates:
                organisations.setdefault(org.id, org)
        # One retrieval span per record: this is the evidence the linter matches on.
        for sid, retrieved in records.items():
            with retrieval_span(ctx.tracer, sid, retrieved.content_hash()):
                pass
        for oid, org in organisations.items():
            with retrieval_span(ctx.tracer, oid, organisation_hash(org)):
                pass

        queries = [
            f"{actor.role.value}: {actor.fairsharing_id or repr(name)}"
            for actor, wanted in searched
            for name in ([actor.fairsharing_id] if actor.fairsharing_id else wanted)
        ]
        queries += [f"ror: {actor.ror_id or repr(actor.name)}" for actor, _ in ambiguous]
        queries += [f"ror: {actor.ror_id or repr(actor.name)}" for actor, _ in resolved]
        queries += queries_extra
        ror_note = (
            f" ROR was not consulted ({ror_unavailable}); funders were searched by the name given."
            if ror_unavailable
            else ""
        )
        opf_note = ""
        if self.opf is None and any(
            a.role in (ActorRole.FUNDER, ActorRole.JOURNAL) for a in actors
        ):
            opf_note = (
                " Open Policy Finder was not searched: no OPEN_POLICY_FINDER_API_KEY is set, so "
                "funders' and journals' open access policies were not checked."
            )
        if problems:
            opf_note += (
                " Not every registry could be asked: " + "; ".join(dict.fromkeys(problems)) + "."
            )
        questions = " ".join(
            [_ambiguity(actor, candidates) for actor, candidates in ambiguous]
            + [_journal_ambiguity(actor, candidates) for actor, candidates in ambiguous_journals]
        )
        funders = [
            ResolvedFunder(
                actor=actor.name,
                crossref_funder_id=org.crossref_funder_preferred,
                grounded_on=[_org_ref(org)],
            )
            for actor, org in resolved
        ]
        resolved_journals = [
            ResolvedJournal(
                actor=actors[n].name,
                publisher=j.publisher,
                issn=j.issn,
                grounded_on=[_ref(r) for r in (j.record, j.crossref) if r is not None],
            )
            for n, j in journals.items()
            if not j.candidates and (j.record or j.crossref)
        ]
        unresolved = [
            AmbiguousActor(
                actor=actor.name,
                role=actor.role,
                grounded_on=[_org_ref(o) for o in candidates],
            )
            for actor, candidates in ambiguous
        ] + [
            AmbiguousActor(actor=actor.name, role=actor.role, grounded_on=[_ref(c) for c in cands])
            for actor, cands in ambiguous_journals
        ]
        labels = [where] + [
            ref
            for ref, used in (
                (ror_where, ror_where is not None),
                (
                    self.opf.snapshot_ref().as_string() if self.opf else None,
                    bool(opf_matched) or bool(journals),
                ),
                (
                    self.crossref.snapshot_ref().as_string() if self.crossref else None,
                    any(j.crossref or j.candidates for j in journals.values()),
                ),
            )
            if used and ref
        ]
        identified = (
            " Funders identified in ROR: "
            + "; ".join(f"{actor.name!r} as {_candidate(org)}" for actor, org in resolved)
            + f" ({ror_where})."
            if resolved
            else ""
        )
        if resolved_journals:
            identified += (
                " Journals identified: "
                + "; ".join(
                    f"{j.actor!r}, published by {j.publisher or 'a publisher not named'}"
                    for j in resolved_journals
                )
                + "."
            )
        texts = self._read_texts(matched, ctx)
        if not records and not organisations and not texts.readings:
            no_record = [actor.name for actor, _ in searched]
            return abstain(
                ReasonCode.NO_CANDIDATES_RETRIEVED,
                f"No registry ({'; '.join(labels)}) has a policy record for "
                f"{', '.join(no_record)}. Many institutions have none; check the policies "
                "directly, including whether they require a particular repository."
                + texts.note
                + ror_note
                + opf_note,
            )

        # --- assess by rule, then advise ------------------------------------------------------
        items = [
            Item(
                record=record,
                actor=actor,
                obligations=tuple(assess.obligations(record)),
                notes=tuple(assess.notes(record, context)),
            )
            for actor, found in matched
            for record in found
        ] + [
            Item(record=record, actor=actor, obligations=(), notes=())
            for actor, found in opf_matched
            for record in found
        ]
        lookups = Lookups(
            policies=self.fallback if snapshot_ref.stale else self.policies,
            opf=self.opf,
            crossref=self.crossref,
            records=dict(records),
            blocked=frozenset(blocked),
        )
        explanation = self.explainer.explain(context, items, ctx, lookups)
        if explanation.obligations is not None or explanation.notes is not None:
            items = [
                Item(
                    record=item.record,
                    actor=item.actor,
                    obligations=(
                        explanation.obligations[n]
                        if explanation.obligations is not None
                        else item.obligations
                    ),
                    notes=explanation.notes[n] if explanation.notes is not None else item.notes,
                    matched_by=item.matched_by,
                )
                for n, item in enumerate(items)
            ]
        advised: list[tuple[Item, Rationale]] = list(
            zip(items, explanation.rationales, strict=True)
        ) + list(explanation.found)
        # Records a model's tools retrieved, of which those cited are evidence.
        for sid, looked_up in lookups.records.items():
            records.setdefault(sid, looked_up)

        no_record = [
            actor.name
            for actor, _ in searched
            if not any(item.actor.name == actor.name for item, _ in advised)
        ]
        searched_summary = SearchedSummary(
            queries=queries,
            snapshot_ref="; ".join(labels),
            policies_retrieved=len({item.record.source_id for item, _ in advised}),
        )
        remarks = " ".join(explanation.remarks)
        cited: dict[str, SourceRecord] = {}
        for jr in resolved_journals + [u for u in unresolved if u.role == ActorRole.JOURNAL]:
            for grounding in jr.grounded_on:
                if grounding.source_id in records:
                    cited[grounding.source_id] = records[grounding.source_id]
        # No policy, but ROR identified a funder, a journal was identified, or there are
        # candidates to choose from: the payload carries them, grounded on their records.
        if not advised:
            statement = "No policy record was matched." + identified
            if questions:
                statement += " " + questions
            if no_record:
                statement += (
                    f" No registry ({'; '.join(labels)}) has a policy record for "
                    f"{', '.join(no_record)}; check their policies directly, including whether "
                    "they require a particular repository."
                )
            statement += texts.note + ror_note + opf_note
            if remarks:
                statement += " " + remarks
            statement += " Human review is required."
            return AgentResult(
                outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
                payload=PolicyChecks(
                    no_record=no_record,
                    funders=funders,
                    journals=resolved_journals,
                    readings=texts.readings,
                    ambiguous=unresolved,
                    searched=searched_summary,
                    grounded_on=[_ref(r) for _, r in sorted(cited.items())]
                    + [_org_ref(o) for _, o in sorted(organisations.items())]
                    + texts.refs,
                ),
                evidence=self._evidence(cited, self._labels(where, ror_where))
                + self._org_evidence(organisations, ror_where or "")
                + texts.evidence,
                **self._model_use(explanation, texts),
            )

        policies = [
            MatchedPolicy(
                actor=item.actor.name,
                role=item.actor.role,
                registry=_registry(item.record),
                match_derivation=item.matched_by,
                obligations=list(item.obligations),
                notes=list(item.notes),
                rationale=rationale.text,
                rationale_derivation=rationale.derivation,
                grounded_on=[_ref(item.record)],
            )
            for item, rationale in advised
        ]
        stated: dict[str, assess.Stated] = {}
        for item, _ in advised:
            held = stated.get(item.record.source_id)
            obligations = (*held.obligations, *item.obligations) if held else item.obligations
            stated[item.record.source_id] = assess.Stated(item.record, obligations)
        conflicts = [
            PolicyConflict(
                kind=kind,
                description=description,
                grounded_on=[_ref(r) for r in involved],
            )
            for kind, involved, description in assess.conflicts(list(stated.values()))
        ]
        mandated: dict[str, RepositoryRef] = {}
        for item, _ in advised:
            if isinstance(item.record, PolicyRecord):
                for ref in assess.mandated(item.record):
                    mandated.setdefault(ref.name.casefold(), ref)
        named_repositories = sorted(
            {
                o.value
                for item, _ in advised
                for o in item.obligations
                if o.kind.value == "repository"
                and o.strength == Strength.REQUIRED
                and o.derivation == Derivation.MODEL
                and o.value
            }
        )
        for item, _ in advised:
            cited[item.record.source_id] = item.record

        evidence = self._evidence(cited, self._labels(where, ror_where))
        actors_matched = len({item.actor.name for item, _ in advised})
        by_model = sum(1 for item, _ in advised if item.matched_by == Derivation.MODEL)
        quoted = sum(
            1 for item, _ in advised for o in item.obligations if o.derivation == Derivation.MODEL
        )
        registries = sorted({item.record.registry for item, _ in advised})
        statement = (
            f"Policies matched: {len(policies)} for {actors_matched} of {len(actors)} actor(s), "
            f"from {' and '.join(registries)} ({'; '.join(labels)})."
        )
        if by_model:
            statement += f" Of these, {by_model} were found by a model with its search tools."
        if quoted:
            statement += (
                f" Obligations read from the records' text by a model: {quoted}, each with a "
                "quote found in its record."
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
        if named_repositories:
            statement += (
                " Repositories a policy's text requires, as a model read it (quoted in the "
                "obligations): " + "; ".join(named_repositories) + "."
            )
        read_required = any(
            o.kind.value == "repository" and o.strength == Strength.REQUIRED
            for r in texts.readings
            for o in r.stated
        )
        if not mandated and not named_repositories and not read_required:
            statement += (
                " No matched record names a required repository. The registries' records do "
                "not always say which repositories a policy requires, so this is not evidence "
                "that none is required: check each policy's own text before choosing a "
                "repository."
            )
        if no_record:
            statement += (
                f" No policy record for: {', '.join(no_record)}; what they require, including "
                "any required repository, was not checked."
            )
        statement += texts.note + ror_note + opf_note
        if remarks:
            statement += " " + remarks
        statement += " Human review is required."
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
            payload=PolicyChecks(
                policies=policies,
                conflicts=conflicts,
                mandated_repositories=list(mandated.values()),
                no_record=no_record,
                funders=funders,
                journals=resolved_journals,
                readings=texts.readings,
                ambiguous=unresolved,
                searched=searched_summary,
                grounded_on=[_ref(r) for _, r in sorted(cited.items())]
                + [_org_ref(o) for _, o in sorted(organisations.items())]
                + texts.refs,
            ),
            evidence=evidence + self._org_evidence(organisations, ror_where or "") + texts.evidence,
            **self._model_use(explanation, texts),
        )

    def _read_texts(
        self, matched: list[tuple[Actor, list[PolicyRecord]]], ctx: RunContext
    ) -> TextReadings:
        """Fetch and read each policy's own text: the page each matched record names, and each
        `policy_url` given. Every page is fetched, with its retrieval span, before any model is
        called (docs/specs/grounding.md, G1)."""
        out = TextReadings()
        wanted = reading_targets(matched)
        if not wanted:
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
        unread: list[str] = []
        now = datetime.now(UTC)
        for fetched in fetch_pages(self.pages, wanted, ctx):
            url, actor, origin, page, problem = fetched
            record_refs = [_ref(origin)] if origin is not None else []
            if page is None:
                if record_refs:
                    out.readings.append(unread_reading(fetched, record_refs))
                else:
                    unread.append(f"{url} ({problem})")
                continue
            reading = self.extractor.extract(actor, page, ctx, out.calls)
            out.calls = reading.calls or out.calls
            out.input_tokens += reading.usage.input_tokens or 0
            out.output_tokens += reading.usage.output_tokens or 0
            ref = text_ref(page)
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
        records = {r.source_id: r for _, found in matched for r in found}
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

    def _model_use(self, explanation: Explanation, texts: TextReadings) -> dict[str, Any]:
        """The models called in this run, their tokens, calls and prompts: the explainer's and
        the extractor's together."""
        logs = [log for log in (explanation.calls, texts.calls) if log]
        if not logs:
            return {
                "input_tokens": explanation.usage.input_tokens,
                "output_tokens": explanation.usage.output_tokens,
            }

        def total(a: int | None, b: int) -> int | None:
            return None if a is None and not b else (a or 0) + b

        return {
            "model_id": (explanation.calls and self.explainer.model_id)
            or (texts.calls and self.extractor.model_id)
            or None,
            "input_tokens": total(explanation.usage.input_tokens, texts.input_tokens),
            "output_tokens": total(explanation.usage.output_tokens, texts.output_tokens),
            "model_calls": tuple(c for log in logs for c in log.calls),
            "prompts": {k: v for log in logs for k, v in log.prompts.items()},
        }

    def _labels(self, where: str, ror_where: str | None) -> dict[str, str]:
        """The `snapshot_ref` of each registry's evidence."""
        return {
            "FAIRsharing": where,
            "Open Policy Finder": self.opf.snapshot_ref().as_string() if self.opf else "",
            "Crossref": self.crossref.snapshot_ref().as_string() if self.crossref else "",
        }

    @staticmethod
    def _evidence(records: dict[str, SourceRecord], labels: dict[str, str]) -> list[EvidenceItem]:
        now = datetime.now(UTC)
        return [
            EvidenceItem(
                source_id=sid,
                source_uri=record.source_uri,
                retrieved_at=now,
                snapshot_ref=labels.get(record.registry) or None,
                hash_algorithm=HASH_ALGORITHM,
                canonicalisation=DOCUMENT_CANONICALISATION,
                content_hash=record.content_hash(),
                content=record.document(),
            )
            for sid, record in sorted(records.items())
        ]

    @staticmethod
    def _org_evidence(
        organisations: dict[str, Organisation], snapshot_ref: str
    ) -> list[EvidenceItem]:
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

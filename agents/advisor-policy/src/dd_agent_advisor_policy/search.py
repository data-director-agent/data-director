"""The first search, one step per source, before any model is called: each funder identified in
ROR (`resolve.py`), each journal in Open Policy Finder and Crossref (`discover.py`), every actor's
policy in FAIRsharing (`match.py`), then funders' and journals' in Open Policy Finder.

Each step takes what it needs and returns what it found, or, for FAIRsharing, which the agent
cannot do without, the outcome. `first_search` composes them into a `FirstSearch`, which holds
every record retrieved, the evidence a model may read and the payload may cite.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from dd_agent_advisor_policy import discover, match
from dd_agent_advisor_policy.classes import (
    Actor,
    ActorRole,
    AmbiguousActor,
    ResolvedFunder,
    ResolvedJournal,
)
from dd_agent_advisor_policy.crossref import CrossrefJournal, CrossrefJournals
from dd_agent_advisor_policy.grounding import org_ref, organisation_hash, record_ref
from dd_agent_advisor_policy.opf import OpenPolicyFinder, OpfRecord
from dd_agent_advisor_policy.records import PolicyRecord
from dd_agent_advisor_policy.resolve import Ambiguous, Resolution, Resolved, Unknown, names, resolve
from dd_agent_advisor_policy.retrieve import Policies, SourceRecord
from dd_agent_advisor_policy.ror import Organisations
from dd_mcp_pid.ror_records import Organisation
from dd_sdk.agent import AgentResult, RunContext, abstain
from dd_sdk.contract.models import ReasonCode
from dd_sdk.registry import RegistryUnavailable, SnapshotRef
from dd_sdk.tracing import retrieval_span

Matched = list[tuple[Actor, list[PolicyRecord]]]


@dataclass(frozen=True)
class Sources:
    """The registries the agent searches, each with the copy that stands in when it is down."""

    policies: Policies
    fallback: Policies | None = None
    organisations: Organisations | None = None
    organisations_fallback: Organisations | None = None
    opf: OpenPolicyFinder | None = None
    crossref: CrossrefJournals | None = None


# --- ROR -------------------------------------------------------------------------------------


@dataclass
class RorStep:
    """Each actor's resolution in ROR, which copy of ROR answered, and why ROR was not
    consulted, when it was not."""

    resolutions: list[Resolution]
    where: str | None = None
    unavailable: str | None = None

    @property
    def note(self) -> str:
        return (
            f" ROR was not consulted ({self.unavailable}); funders were searched by the name given."
            if self.unavailable
            else ""
        )


def resolve_funders(
    actors: Sequence[Actor],
    organisations: Organisations | None,
    fallback: Organisations | None = None,
) -> RorStep:
    """Identify each funder in ROR. ROR being unavailable does not stop the run: funders are
    then searched by the name given, and the statement says so."""
    unknown: list[Resolution] = [Unknown() for _ in actors]
    if not any(a.role == ActorRole.FUNDER for a in actors):
        return RorStep(unknown)
    if organisations is None:
        return RorStep(unknown, unavailable="no copy of ROR is configured")
    try:
        ref = organisations.snapshot_ref()
        return RorStep([resolve(a, organisations) for a in actors], ref.as_string())
    except RegistryUnavailable as exc:
        if fallback is None:
            return RorStep(unknown, unavailable=str(exc))
        try:
            found = [resolve(a, fallback) for a in actors]
        except RegistryUnavailable as again:
            return RorStep(unknown, unavailable=f"{exc}; {again}")
        stale = SnapshotRef(label=fallback.snapshot_ref().label, stale=True)
        return RorStep(found, stale.as_string())


# --- journals --------------------------------------------------------------------------------


def identify_journals(
    actors: Sequence[Actor], opf: OpenPolicyFinder | None, crossref: CrossrefJournals | None
) -> dict[int, discover.Journal]:
    """What Open Policy Finder and Crossref say about each journal given by name or ISSN, by the
    actor's position."""
    if opf is None and crossref is None:
        return {}
    return {
        n: discover.journal(actor, opf, crossref)
        for n, actor in enumerate(actors)
        if actor.role == ActorRole.JOURNAL and not actor.fairsharing_id
    }


# --- FAIRsharing -----------------------------------------------------------------------------


def _match_all(searched: list[tuple[Actor, list[str]]], source: Policies) -> Matched:
    return [(actor, match.match(actor, source, wanted)) for actor, wanted in searched]


def search_fairsharing(
    searched: list[tuple[Actor, list[str]]], policies: Policies, fallback: Policies | None
) -> tuple[Matched, SnapshotRef] | AgentResult:
    """Each actor's FAIRsharing policy records, and which copy answered; the outcome when
    neither FAIRsharing nor its snapshot could be searched."""
    snapshot_ref = policies.snapshot_ref()
    try:
        return _match_all(searched, policies), snapshot_ref
    except RegistryUnavailable as exc:
        if fallback is None:
            return abstain(
                ReasonCode.REGISTRY_UNAVAILABLE,
                f"FAIRsharing could not be searched: {exc}. This is not an empty result.",
            )
        try:
            matched = _match_all(searched, fallback)
        except RegistryUnavailable as again:
            return abstain(
                ReasonCode.REGISTRY_UNAVAILABLE,
                f"FAIRsharing could not be searched ({exc}), nor its snapshot ({again}).",
            )
        stale = SnapshotRef(
            label=fallback.snapshot_ref().label,
            stale=True,
            notes=[f"live route failed: {exc}"],
        )
        return matched, stale


# --- Open Policy Finder ----------------------------------------------------------------------


@dataclass
class OpfStep:
    """Funders' and journals' Open Policy Finder records, the queries made, and the registries
    that could not be asked."""

    matched: list[tuple[Actor, list[OpfRecord]]] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def search_opf(
    searched: list[tuple[Actor, list[str]]],
    actors: Sequence[Actor],
    journals: dict[int, discover.Journal],
    opf: OpenPolicyFinder | None,
) -> OpfStep:
    """Each funder searched in Open Policy Finder by its names, and each journal's own record,
    or its publishers' when it has none. A registry that cannot be asked is noted."""
    out = OpfStep()
    by_name = {a.name: n for n, a in enumerate(actors)}
    for actor, wanted in searched:
        n = by_name[actor.name]
        if actor.role == ActorRole.FUNDER and opf is not None:
            try:
                found, asked = discover.funders(actor, wanted, opf)
                out.queries += asked
                out.matched.append((actor, found))
            except RegistryUnavailable as exc:
                out.problems.append(str(exc))
        elif n in journals:
            journal = journals[n]
            out.queries += journal.queries
            out.problems += journal.problems
            # The journal's own record carries its publishers' policies; a publisher's
            # record stands in only when Open Policy Finder has none for the journal.
            own = [journal.record] if journal.record else journal.publishers
            out.matched.append((actor, own[: discover.PER_ACTOR]))
    for j in journals.values():
        out.queries += [q for q in j.queries if q not in out.queries] if j.candidates else []
    return out


# --- the search as a whole -------------------------------------------------------------------


@dataclass
class FirstSearch:
    """Everything the first search found, and every record it retrieved."""

    sources: Sources
    actors: list[Actor]
    ror: RorStep
    journals: dict[int, discover.Journal]
    searched: list[tuple[Actor, list[str]]]
    blocked: set[str]
    matched: Matched = field(default_factory=list)
    snapshot_ref: SnapshotRef = field(default_factory=lambda: SnapshotRef(label=""))
    opf: OpfStep = field(default_factory=OpfStep)
    records: dict[str, SourceRecord] = field(default_factory=dict)
    organisations: dict[str, Organisation] = field(default_factory=dict)

    @property
    def where(self) -> str:
        return self.snapshot_ref.as_string()

    @property
    def resolved(self) -> list[tuple[Actor, Organisation]]:
        return [
            (actor, r.organisation)
            for actor, r in zip(self.actors, self.ror.resolutions, strict=True)
            if isinstance(r, Resolved)
        ]

    @property
    def ambiguous(self) -> list[tuple[Actor, tuple[Organisation, ...]]]:
        return [
            (actor, r.candidates)
            for actor, r in zip(self.actors, self.ror.resolutions, strict=True)
            if isinstance(r, Ambiguous)
        ]

    @property
    def ambiguous_journals(self) -> list[tuple[Actor, list[OpfRecord | CrossrefJournal]]]:
        return [
            (self.actors[n], list(j.candidates)) for n, j in self.journals.items() if j.candidates
        ]

    def collect(self) -> None:
        """Gather every record retrieved, which a model may read and the payload may cite."""
        for _, fs in self.matched:
            for fs_record in fs:
                self.records.setdefault(fs_record.source_id, fs_record)
        for _, opf_records in self.opf.matched:
            for opf_record in opf_records:
                self.records.setdefault(opf_record.source_id, opf_record)
        for journal in self.journals.values():
            for other in (
                journal.record,
                journal.crossref,
                *journal.publishers,
                *journal.candidates,
            ):
                if other is not None:
                    self.records.setdefault(other.source_id, other)
        self.organisations = {org.id: org for _, org in self.resolved}
        for _, candidates in self.ambiguous:
            for org in candidates:
                self.organisations.setdefault(org.id, org)

    def emit_spans(self, ctx: RunContext) -> None:
        """One retrieval span per record: this is the evidence the linter matches on."""
        for sid, retrieved in self.records.items():
            with retrieval_span(ctx.tracer, sid, retrieved.content_hash()):
                pass
        for oid, org in self.organisations.items():
            with retrieval_span(ctx.tracer, oid, organisation_hash(org)):
                pass

    def queries(self) -> list[str]:
        out = [
            f"{actor.role.value}: {actor.fairsharing_id or repr(name)}"
            for actor, wanted in self.searched
            for name in ([actor.fairsharing_id] if actor.fairsharing_id else wanted)
        ]
        out += [f"ror: {actor.ror_id or repr(actor.name)}" for actor, _ in self.ambiguous]
        out += [f"ror: {actor.ror_id or repr(actor.name)}" for actor, _ in self.resolved]
        return out + self.opf.queries

    def funders(self) -> list[ResolvedFunder]:
        return [
            ResolvedFunder(
                actor=actor.name,
                crossref_funder_id=org.crossref_funder_preferred,
                grounded_on=[org_ref(org)],
            )
            for actor, org in self.resolved
        ]

    def resolved_journals(self) -> list[ResolvedJournal]:
        return [
            ResolvedJournal(
                actor=self.actors[n].name,
                publisher=j.publisher,
                issn=j.issn,
                grounded_on=[record_ref(r) for r in (j.record, j.crossref) if r is not None],
            )
            for n, j in self.journals.items()
            if not j.candidates and (j.record or j.crossref)
        ]

    def unresolved(self) -> list[AmbiguousActor]:
        return [
            AmbiguousActor(
                actor=actor.name,
                role=actor.role,
                grounded_on=[org_ref(o) for o in candidates],
            )
            for actor, candidates in self.ambiguous
        ] + [
            AmbiguousActor(
                actor=actor.name, role=actor.role, grounded_on=[record_ref(c) for c in cands]
            )
            for actor, cands in self.ambiguous_journals
        ]

    def labels(self) -> list[str]:
        """The `snapshot_ref` of each registry that was used."""
        opf, crossref = self.sources.opf, self.sources.crossref
        return [self.where] + [
            ref
            for ref, used in (
                (self.ror.where, self.ror.where is not None),
                (
                    opf.snapshot_ref().as_string() if opf else None,
                    bool(self.opf.matched) or bool(self.journals),
                ),
                (
                    crossref.snapshot_ref().as_string() if crossref else None,
                    any(j.crossref or j.candidates for j in self.journals.values()),
                ),
            )
            if used and ref
        ]

    def registry_labels(self) -> dict[str, str]:
        """The `snapshot_ref` of each registry's evidence."""
        opf, crossref = self.sources.opf, self.sources.crossref
        return {
            "FAIRsharing": self.where,
            "Open Policy Finder": opf.snapshot_ref().as_string() if opf else "",
            "Crossref": crossref.snapshot_ref().as_string() if crossref else "",
        }


def _searched(
    actors: list[Actor], ror: RorStep, journals: dict[int, discover.Journal], blocked: set[str]
) -> list[tuple[Actor, list[str]]]:
    """The names each actor is searched by. An ambiguous funder or journal is not searched: its
    policy is looked up once the researcher says which they mean. A journal is searched by its
    publisher's names too."""
    return [
        (actor, names(actor, r) + (journals[n].publisher_names if n in journals else []))
        for n, (actor, r) in enumerate(zip(actors, ror.resolutions, strict=True))
        if actor.name not in blocked
    ]


def first_search(actors: list[Actor], sources: Sources) -> FirstSearch | AgentResult:
    """Every step of the first search, in order; the outcome when FAIRsharing cannot be asked."""
    found = FirstSearch(
        sources=sources,
        actors=actors,
        ror=resolve_funders(actors, sources.organisations, sources.organisations_fallback),
        journals=identify_journals(actors, sources.opf, sources.crossref),
        searched=[],
        blocked=set(),
    )
    found.blocked = {a.name for a, _ in found.ambiguous} | {
        a.name for a, _ in found.ambiguous_journals
    }
    found.searched = _searched(actors, found.ror, found.journals, found.blocked)
    fairsharing = search_fairsharing(found.searched, sources.policies, sources.fallback)
    if isinstance(fairsharing, AgentResult):
        return fairsharing
    found.matched, found.snapshot_ref = fairsharing
    found.opf = search_opf(found.searched, actors, found.journals, sources.opf)
    found.collect()
    return found

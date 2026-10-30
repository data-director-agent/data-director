"""The policy advisor: retrieve → match → assess → explain, over FAIRsharing's policy records.

It serves the first step of Phase 2 (Figure 2), checking funder, journal and institutional data
sharing policies, and the first step of Phase 3 (Figure 3), whether the funder, journal or
institution mandates a repository. The repositories a policy requires are returned in the form
`advisor.repository` takes as `RepositoryNeeds.mandated`.

Grounding invariant: retrieval precedes any model call, and the model never determines which
policies are matched or what any obligation is. A matched policy names its record once, in
`grounded_on`; what the reader is shown about it is the evidence item's `content`, which the
linter re-hashes (E1, ADR-0015). Where policies differ, the agent flags it for human review and
never decides which applies.
"""

from __future__ import annotations

from datetime import UTC, datetime

from dd_agent_advisor_policy import assess, match
from dd_agent_advisor_policy.classes import (
    Actor,
    MatchedPolicy,
    PolicyChecks,
    PolicyConflict,
    PolicyContext,
    RepositoryRef,
    SearchedSummary,
)
from dd_agent_advisor_policy.explain import Explainer, Item, TemplateExplainer
from dd_agent_advisor_policy.records import PolicyRecord
from dd_agent_advisor_policy.retrieve import Policies, RegistryUnavailable, SnapshotRef
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


def _ref(record: PolicyRecord) -> GroundingRef:
    return GroundingRef(source_id=record.fairsharing_id, content_hash=record.content_hash())


def _matched(actors: list[Actor], source: Policies) -> list[tuple[Actor, list[PolicyRecord]]]:
    return [(actor, match.match(actor, source)) for actor in actors]


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
        },
        serves=("governance.policies", "repository.mandated"),
    )

    def __init__(
        self,
        policies: Policies,
        explainer: Explainer | None = None,
        fallback: Policies | None = None,
    ) -> None:
        self.policies = policies
        self.fallback = fallback
        self.explainer = explainer or TemplateExplainer()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        context = request.input
        assert isinstance(context, PolicyContext)  # the conductor checked spec.accepts
        if not context.actors:
            return _abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "The context names no funder, journal or institution, so there was no policy "
                "to look up.",
            )

        snapshot_ref = self.policies.snapshot_ref()
        try:
            matched = _matched(context.actors, self.policies)
        except RegistryUnavailable as exc:
            if self.fallback is None:
                return _abstain(
                    ReasonCode.REGISTRY_UNAVAILABLE,
                    f"FAIRsharing could not be searched: {exc}. This is not an empty result.",
                )
            try:
                matched = _matched(context.actors, self.fallback)
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
        # One retrieval span per record: this is the evidence the linter matches on.
        for fid, record in records.items():
            with retrieval_span(ctx.tracer, fid, record.content_hash()):
                pass

        queries = [f"{a.role.value}: {a.fairsharing_id or repr(a.name)}" for a in context.actors]
        no_record = [actor.name for actor, found in matched if not found]
        if not records:
            return _abstain(
                ReasonCode.NO_CANDIDATES_RETRIEVED,
                f"FAIRsharing ({where}) has no policy record for {', '.join(no_record)}. "
                "Many institutions have none; check the policies directly.",
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
            f"{len(context.actors) - len(no_record)} of {len(context.actors)} actor(s), "
            f"grounded in {len(evidence)} FAIRsharing record(s) ({where})."
        )
        if conflicts:
            statement += (
                f" Obligations the policies state differently: {len(conflicts)}; a person "
                "should decide which applies."
            )
        if mandated:
            statement += " Repositories required: " + ", ".join(r.name for r in mandated.values())
            statement += "."
        else:
            statement += " No matched record names a required repository."
        if no_record:
            statement += f" No policy record for: {', '.join(no_record)}."
        statement += " Human review is required."
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
            payload=PolicyChecks(
                policies=policies,
                conflicts=conflicts,
                mandated_repositories=list(mandated.values()),
                no_record=no_record,
                searched=SearchedSummary(
                    queries=queries, snapshot_ref=where, policies_retrieved=len(records)
                ),
                grounded_on=[_ref(r) for _, r in sorted(records.items())],
            ),
            evidence=evidence,
            model_id=self.explainer.model_id,
            input_tokens=explanation.usage.input_tokens,
            output_tokens=explanation.usage.output_tokens,
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

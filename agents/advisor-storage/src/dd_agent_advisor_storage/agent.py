"""advisor.storage: the Storage Adviser.

It serves the process flow's step for planning where a project's data are stored, backed up and
kept secure while it runs (`setup.storage`). It recommends only from the storage services the
deployment's profile names as its institution's (`institution_storage`), which the conductor
fills into its input; no registry lists an institution's storage, so with none named it abstains
and points the researcher to their institution's research data staff.

Grounding mode `retrieval` (docs/specs/grounding.md): each service it names rests on what the
profile vouches for about it, cited under the profile's reference, which the harness's source
check resolves against the profile it loaded. Its decisions are rules (`rules`); a summariser
(`dd_sdk.summary`) then writes a short summary beside them, a model's by default, which changes
none of them. Where the data involve personal data and no service is approved for them, the
choice is a person's: it refers the step rather than offer storage it cannot stand behind.
"""

from __future__ import annotations

from datetime import UTC, datetime

from dd_agent_advisor_storage import rules
from dd_agent_advisor_storage.classes import (
    ExcludedStorage,
    PersonalDataAnswer,
    StorageAdvice,
    StorageNeeds,
    StorageOption,
)
from dd_sdk import summary
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext, abstain
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.facts import InstitutionStorage
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

# Who decides where personal data are kept when no approved service is named: the deployment's
# data stewards, who know its data protection staff (docs/specs/stewardship.md).
DATA_STEWARD = "data_steward"
# The evidence identifier of what the profile vouches for about one storage service.
SOURCE_PREFIX = "institution-storage:"
LIMITATIONS = (
    "It recommends only from the storage services your institution's profile names, and knows "
    "of them only what the profile says.",
    "It does not book storage, set up backups or check how a service is configured.",
    "It does not advise on anonymisation or decide how sensitive data are protected: that is "
    "for your institution's ethics and data protection staff.",
    "Its summary is written by a model from the findings alone unless the template is chosen; "
    "the findings above it are the agent's judgement, not the summary.",
)


class StorageAdviser:
    spec = AgentSpec(
        agent_id="advisor.storage",
        version="0.1.0a1",
        title="Storage Adviser",
        description=(
            "Recommends where to store and back up a project's data while it runs, from the "
            "storage services the institution's profile names, leaving out any not approved "
            "for personal data when the data involve them, and lists the questions a storage "
            "and backup plan answers. Rules only; it cites what the profile vouches for."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(StorageNeeds),),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload=ClassSchema.of(StorageAdvice),
        derivations={
            "storage_options.storage_id": Derived(Derivation.LEXICAL),
            "storage_options.offers": Derived(Derivation.TEMPLATE),
            "storage_options.concerns": Derived(Derivation.TEMPLATE),
            "excluded_storage.storage_id": Derived(Derivation.LEXICAL),
            "excluded_storage.excluded_because": Derived(Derivation.TEMPLATE),
            "plan_questions": Derived(Derivation.TEMPLATE),
            "summary": Derived(Derivation.MODEL, recorded_in="summary_derivation"),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("setup.storage",),
    )

    def __init__(self, summariser: summary.Summariser | None = None) -> None:
        self.summariser = summariser or summary.TemplateSummariser()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        needs = request.input
        assert isinstance(needs, StorageNeeds)
        if not needs.institution_storage:
            return abstain(
                ReasonCode.NO_CANDIDATES_RETRIEVED,
                "This deployment's profile names none of your institution's storage services. "
                "Your institution's research data staff can say which storage is approved.",
            )
        judgement = rules.judge(needs)
        if not judgement.options and needs.involves_personal_data is PersonalDataAnswer.YES:
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.REFERRED,
                    reason_code=ReasonCode.REQUIRES_HUMAN_JUDGEMENT,
                    referred_to=DATA_STEWARD,
                    statement=(
                        "The data involve personal data, and the profile names no storage "
                        "service approved for them. Where to keep them is for your institution's "
                        "data protection and research data staff to decide."
                    ),
                )
            )
        cited = [j.entry for j in judgement.options] + [e for e, _ in judgement.excluded]
        for entry in cited:
            with retrieval_span(ctx.tracer, source_id(entry), _hash(entry)):
                pass
        now = datetime.now(UTC)
        options = [
            StorageOption(
                storage_id=j.entry.storage_id,
                offers=j.offers,
                concerns=j.concerns,
                grounded_on=[_ref(j.entry)],
            )
            for j in judgement.options
        ]
        excluded = [
            ExcludedStorage(storage_id=e.storage_id, excluded_because=why, grounded_on=[_ref(e)])
            for e, why in judgement.excluded
        ]
        statement = (
            f"{len(options)} of your institution's storage services may hold the data"
            f"{f', and {len(excluded)} are left out' if excluded else ''}. "
            "From the institution's profile, by rule; you choose."
        )
        told = summary.Findings(
            {
                "needs": needs.model_dump(
                    mode="json", exclude_none=True, exclude={"institution_storage"}
                ),
                "storage_options": [
                    o.model_dump(mode="json", exclude={"grounded_on"}) for o in options
                ],
                "excluded_storage": [
                    e.model_dump(mode="json", exclude={"grounded_on"}) for e in excluded
                ],
                "plan_questions": judgement.questions,
            },
            statement,
        )
        summarised, explanation = summary.summarise(self.summariser, told, ctx)
        result = AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
            payload=StorageAdvice(
                storage_options=options,
                excluded_storage=excluded,
                plan_questions=judgement.questions,
                summary=summarised.text,
                summary_derivation=summarised.derivation,
                limitations=list(LIMITATIONS),
                grounded_on=[_ref(entry) for entry in cited],
            ),
            evidence=[_evidence(entry, now) for entry in cited],
        )
        return summary.with_calls(result, self.summariser.model_id, explanation)


def source_id(entry: InstitutionStorage) -> str:
    return f"{SOURCE_PREFIX}{entry.storage_id}"


def _hash(entry: InstitutionStorage) -> str:
    return content_hash(entry.model_dump(mode="json"), DOCUMENT_CANONICALISATION)


def _ref(entry: InstitutionStorage) -> GroundingRef:
    return GroundingRef(source_id=source_id(entry), content_hash=_hash(entry))


def _evidence(entry: InstitutionStorage, now: datetime) -> EvidenceItem:
    """What the profile vouches for about a service, cited under the profile's reference."""
    return EvidenceItem(
        source_id=source_id(entry),
        source_uri=entry.guidance[0] if entry.guidance else None,
        retrieved_at=now,
        snapshot_ref=entry.profile_ref,
        hash_algorithm=HASH_ALGORITHM,
        canonicalisation=DOCUMENT_CANONICALISATION,
        content_hash=_hash(entry),
        content=entry.model_dump(mode="json"),
    )

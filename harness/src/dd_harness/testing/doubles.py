"""Scripted doubles: agents whose behaviour a test sets.

`AbstainingStub` abstains unconditionally under the fixed id `stub.abstain`, which the test profiles
name, so a test can exercise the gate, the store and the non-success path without scripting
anything. `DocumentStub`, under `stub.document`, drafts a placeholder project document of whichever
kind it is asked for (docs/specs/projects.md). `ScriptedAgent` is a generic double whose
specification and behaviour are set per test. It emits the spans a test asks for, then returns (or
raises) what it was given, so harness and linter behaviour can be pinned for each grounding mode
without a retrieval backend or a model. Nothing here knows about any real agent.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from dd_harness.testing.classes import (
    ProbeCheck,
    ProbeClaim,
    ProbeDocumentRequest,
    ProbeProfile,
    ProbeRecord,
    ProbeReview,
)
from dd_sdk.agent import AgentResult, AgentSpec, ModelUse, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    Document,
    DocumentKind,
    DocumentQuestion,
    DraftRequest,
    EvidenceItem,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Message,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    Reply,
)
from dd_sdk.evidence import (
    DOCUMENT_CANONICALISATION,
    HASH_ALGORITHM,
    INPUT_CANONICALISATION,
    content_hash,
)
from dd_sdk.prompts import ModelCallLog
from dd_sdk.tracing import chat_span, retrieval_span

# The provider a double that stands for a model-backed agent names. No model is called.
MODEL_PROVIDER = "test"

# The question a DocumentStub with `asks` puts to the researcher.
STUB_QUESTION = DocumentQuestion(
    question_id="q-" + "0" * 16,
    question_prompt="What does the dataset describe?",
    gap_section="Description",
)

Behaviour = AgentResult | Exception | Callable[[InvocationRequest, RunContext], AgentResult]


@dataclass(frozen=True)
class Retrieve:
    """Emit a retrieval span for one source document before the result is produced."""

    source_id: str
    document: dict[str, Any]

    @property
    def content_hash(self) -> str:
        return content_hash(self.document, DOCUMENT_CANONICALISATION)

    def ref(self) -> GroundingRef:
        return GroundingRef(source_id=self.source_id, content_hash=self.content_hash)

    def evidence(self) -> EvidenceItem:
        return EvidenceItem(
            source_id=self.source_id,
            retrieved_at=datetime.now(UTC),
            hash_algorithm=HASH_ALGORITHM,
            canonicalisation=DOCUMENT_CANONICALISATION,
            content_hash=self.content_hash,
        )


@dataclass(frozen=True)
class Chat:
    """Emit a chat span (a model call) before the result is produced."""

    model_id: str = "fake-model"


SPECS: dict[GroundingMode, AgentSpec] = {
    GroundingMode.RETRIEVAL: AgentSpec(
        agent_id="fake.retrieval",
        version="0",
        description="Scripted retrieval-mode agent.",
        action_class="advise",
        accepts=(ClassSchema.of(ProbeClaim),),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload=ClassSchema.of(ProbeCheck),
    ),
    GroundingMode.INPUT_ONLY: AgentSpec(
        agent_id="fake.input-only",
        version="0",
        description="Scripted input-only agent.",
        action_class="advise",
        accepts=(ClassSchema.of(ProbeRecord),),
        grounding_mode=GroundingMode.INPUT_ONLY,
        payload=ClassSchema.of(ProbeReview),
    ),
    GroundingMode.NONE: AgentSpec(
        agent_id="fake.none",
        version="0",
        description="Scripted deterministic agent.",
        action_class="advise",
        accepts=(ClassSchema.of(ProbeRecord), ClassSchema.of(ProbeProfile)),
        grounding_mode=GroundingMode.NONE,
        payload=ClassSchema.of(ProbeReview),
    ),
    GroundingMode.DELEGATION: AgentSpec(
        agent_id="fake.delegation",
        version="0",
        description="Scripted delegation-mode agent.",
        action_class="advise",
        accepts=(ClassSchema.of(Message),),
        grounding_mode=GroundingMode.DELEGATION,
        payload=ClassSchema.of(Reply),
    ),
}


class ScriptedAgent:
    def __init__(
        self,
        mode: GroundingMode,
        behaviour: Behaviour,
        steps: Iterable[Retrieve | Chat] = (),
        **spec_overrides: Any,
    ) -> None:
        self.spec = replace(SPECS[mode], **spec_overrides)
        self.behaviour = behaviour
        self.steps = list(steps)
        self.calls = 0

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        self.calls += 1
        for step in self.steps:
            if isinstance(step, Retrieve):
                with retrieval_span(ctx.tracer, step.source_id, step.content_hash):
                    pass
            else:
                with chat_span(ctx.tracer, step.model_id):
                    pass
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        if isinstance(self.behaviour, AgentResult):
            return self.behaviour
        return self.behaviour(request, ctx)


class AbstainingStub:
    """Abstains unconditionally with `capability_not_implemented`. It accepts the core's
    `Message` (docs/specs/contract.md) and declares grounding mode `none`."""

    spec = AgentSpec(
        agent_id="stub.abstain",
        version="0.3.0",
        description="Abstains unconditionally; exercises the non-success path.",
        action_class="advise",
        accepts=(ClassSchema.of(Message),),
        grounding_mode=GroundingMode.NONE,
        payload=None,
    )

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.ABSTAINED,
                reason_code=ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
                statement=(
                    "This agent is a stub and abstains unconditionally. No registry was searched "
                    "and no model was called."
                ),
            )
        )


# What `DocumentStub` drafts for each kind: a media type and a placeholder text in it.
_DRAFTS: dict[DocumentKind, tuple[str, str]] = {
    DocumentKind.METADATA_RECORD: (
        "application/json",
        '{"title": "Untitled dataset", "description": "Drafted by a stub."}',
    ),
    DocumentKind.README: ("text/markdown", "# Untitled dataset\n\nDrafted by a stub.\n"),
    DocumentKind.DATA_DICTIONARY: ("text/csv", "field,description\nid,Drafted by a stub.\n"),
    DocumentKind.DMP: ("text/markdown", "# Data management plan\n\nDrafted by a stub.\n"),
    DocumentKind.OTHER: ("text/plain", "Drafted by a stub.\n"),
}


class DocumentStub:
    """Drafts a placeholder `Document` of the kind a `ProbeDocumentRequest` or a core
    `DraftRequest` names, from a fixed template, grounded on its input. It declares grounding mode
    `none`. For a `DraftRequest` it says which facts it was given, so a test can see what the
    conductor put in, and revises the `current_version` it was given, if any.

    Given a `model_id`, it stands for a drafter that writes with a language model: it records one
    model call, as a real agent would through `dd_sdk.prompts`, without calling any model, and
    says its draft was derived by `model` (docs/specs/disclosure.md). With `asks`, its draft asks
    `STUB_QUESTION` (docs/specs/drafting.md). Given any `draft_answers`, it says how many."""

    spec = AgentSpec(
        agent_id="stub.document",
        version="0.1.0",
        description="Drafts a placeholder project document of the kind it is asked for.",
        action_class="advise",
        accepts=(ClassSchema.of(ProbeDocumentRequest), ClassSchema.of(DraftRequest)),
        grounding_mode=GroundingMode.NONE,
        payload=ClassSchema.of(Document),
    )

    def __init__(self, model_id: str | None = None, *, asks: bool = False) -> None:
        self.model_id = model_id
        self.asks = asks
        if model_id is not None:
            # A model call is allowed in input_only, not in none (docs/specs/grounding.md).
            self.spec = replace(
                self.spec,
                grounding_mode=GroundingMode.INPUT_ONLY,
                models=(ModelUse(MODEL_PROVIDER, model_id, "local"),),
            )

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        asked = request.input
        # The conductor checked spec.accepts.
        assert isinstance(asked, ProbeDocumentRequest | DraftRequest)
        kind = asked.document_kind
        media_type, text = _DRAFTS[kind]
        calls = ModelCallLog(MODEL_PROVIDER)
        if self.model_id is not None:
            with chat_span(ctx.tracer, self.model_id):
                calls.record(
                    {
                        "system": "Draft the document asked for.",
                        "messages": [{"role": "user", "content": f"Draft a {kind.value}."}],
                    },
                    self.model_id,
                    input_tokens=12,
                    output_tokens=34,
                )
        revises = None
        if isinstance(asked, DraftRequest):
            files = len(asked.inventory.inventory_files) if asked.inventory else None
            repository = asked.requirements.repository_name if asked.requirements else None
            text += f"\nGiven: files={files}, repository={repository}\n"
            if asked.draft_answers:
                text += f"Answers: {len(asked.draft_answers)}\n"
            revises = asked.current_version.version_ref if asked.current_version else None
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=f"Drafted a placeholder {kind.value}."
                + (" No model was called." if self.model_id is None else ""),
            ),
            payload=Document(
                document_kind=kind,
                media_type=media_type,
                document_text=text,
                document_derivation=Derivation.TEMPLATE
                if self.model_id is None
                else Derivation.MODEL,
                grounded_on=[GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)],
                revises=revises,
                document_questions=[STUB_QUESTION] if self.asks else [],
            ),
            evidence=[
                EvidenceItem(
                    source_id=ctx.input_ref,
                    hash_algorithm=HASH_ALGORITHM,
                    canonicalisation=INPUT_CANONICALISATION,
                    content_hash=ctx.input_hash,
                )
            ],
            model_calls=calls.calls,
            prompts=calls.prompts,
        )

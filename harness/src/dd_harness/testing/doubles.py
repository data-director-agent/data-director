"""Scripted doubles: agents whose behaviour a test sets.

`AbstainingStub` abstains unconditionally under the fixed id `stub.abstain`, which the test
profiles name, so a test can exercise the gate, the store and the non-success path without
scripting anything. `ScriptedAgent` is a generic double whose specification and behaviour are set
per test. It emits the spans a test asks for, then returns (or raises) what it was given, so
harness and linter behaviour can be pinned for each grounding mode without a retrieval backend or
a model. Nothing here knows about any real agent.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from dd_harness.testing.classes import (
    ProbeCheck,
    ProbeClaim,
    ProbeProfile,
    ProbeRecord,
    ProbeReview,
)
from dd_sdk.agent import AgentResult, AgentSpec, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
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
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, HASH_ALGORITHM, content_hash
from dd_sdk.tracing import chat_span, retrieval_span

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
    `Message` (ADR-0019) and declares grounding mode `none`."""

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

"""A test kit for the harness and for agent packages.

`in_process(agent)` serves an agent object with `dd_sdk.serve` on an in-memory httpx ASGI
transport and returns the `RemoteAgent` the workbench would build from its card, so a test
exercises the real A2A wire (request, metadata, spans, spec extension) without a network or a
second process. `make_conductor` does this for every agent it is given, so a harness test runs
an agent the way the workbench runs it in production.

`ScriptedAgent` is a generic double whose specification and behaviour are set per test. It emits
the spans a test asks for, then returns (or raises) what it was given, so harness and linter
behaviour can be pinned for each grounding mode without a retrieval backend or a model. Nothing
here knows about any real agent.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from dd_sdk import serve
from dd_sdk.agent import Agent, AgentResult, AgentSpec, RunContext
from dd_sdk.contract.models import (
    Claim,
    DatasetProfile,
    Derivation,
    EvidenceItem,
    FactCheck,
    Frozen,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    MetadataRecord,
    Outcome,
    OutcomeStatus,
    QualityReview,
    Verdict,
)
from dd_sdk.evidence import (
    DOCUMENT_CANONICALISATION,
    HASH_ALGORITHM,
    INPUT_CANONICALISATION,
    content_hash,
)
from dd_sdk.tracing import chat_span, retrieval_span
from workbench.conductor import Conductor
from workbench.registry import Registry
from workbench.remote import RemoteAgent
from workbench.store import RunStore

PERMISSIVE = "profile:test-permissive"

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
        requirement_ids=(),
        action_class="advise",
        accepts=(Claim,),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload_type=FactCheck,
    ),
    GroundingMode.INPUT_ONLY: AgentSpec(
        agent_id="fake.input-only",
        version="0",
        description="Scripted input-only agent.",
        requirement_ids=(),
        action_class="advise",
        accepts=(MetadataRecord,),
        grounding_mode=GroundingMode.INPUT_ONLY,
        payload_type=QualityReview,
    ),
    GroundingMode.NONE: AgentSpec(
        agent_id="fake.none",
        version="0",
        description="Scripted deterministic agent.",
        requirement_ids=(),
        action_class="advise",
        accepts=(MetadataRecord, DatasetProfile),
        grounding_mode=GroundingMode.NONE,
        payload_type=QualityReview,
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


# --- Results a scripted agent can return ------------------------------------------------------


def input_ref(ctx: RunContext) -> GroundingRef:
    return GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)


def input_evidence(ctx: RunContext) -> EvidenceItem:
    return EvidenceItem(
        source_id=ctx.input_ref,
        hash_algorithm=HASH_ALGORITHM,
        canonicalisation=INPUT_CANONICALISATION,
        content_hash=ctx.input_hash,
    )


def review_of_input(request: InvocationRequest, ctx: RunContext) -> AgentResult:
    """A succeeded QualityReview grounded on the input, as an input_only/none agent should."""
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Reviewed."),
        payload=QualityReview(score=1.0, grounded_on=[input_ref(ctx)]),
        evidence=[input_evidence(ctx)],
    )


def fact_check_over(*sources: Retrieve) -> AgentResult:
    """A succeeded FactCheck grounded on exactly the given sources."""
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Checked."),
        payload=FactCheck(
            verdict=Verdict.SUPPORTED,
            rationale="Scripted.",
            rationale_derivation=Derivation.TEMPLATE,
            grounded_on=[s.ref() for s in sources],
        ),
        evidence=[s.evidence() for s in sources],
    )


SOURCE_A = Retrieve("src:a", {"source_id": "src:a", "text": "Alpha."})
SOURCE_B = Retrieve("src:b", {"source_id": "src:b", "text": "Beta."})


# --- Harness helpers --------------------------------------------------------------------------


def asgi_client_factory(app: Any) -> Callable[[str, float], httpx.AsyncClient]:
    """An httpx client factory bound to one ASGI app, for `RemoteAgent` and `Registry`."""

    def factory(base_url: str, timeout_s: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=base_url, timeout=timeout_s
        )

    return factory


def in_process(agent: Agent, timeout_s: float = 30.0) -> RemoteAgent:
    """Serve `agent` in memory and return the `RemoteAgent` built from its card."""
    base_url = f"http://{agent.spec.agent_id}.agents.test"
    app = serve.app(agent, base_url=base_url)
    return RemoteAgent.from_url(
        base_url, timeout_s=timeout_s, client_factory=asgi_client_factory(app)
    )


def make_conductor(
    runs_dir: Path, *agents: Agent, crate: bool = False, remote: bool = True
) -> Conductor:
    """A conductor over `agents`, each reached over in-process A2A unless `remote` is False."""
    registry = Registry.from_agents(in_process(a) if remote else a for a in agents)
    return Conductor(registry=registry, store=RunStore(runs_dir), write_crate=crate)


def record() -> MetadataRecord:
    return MetadataRecord(
        identifier="https://doi.org/10.15131/shef.data.00000000",
        title="Soil chemistry survey",
        licence="https://creativecommons.org/licenses/by/4.0/",
        creators=["Example Researcher"],
    )


def claim() -> Claim:
    return Claim(text="A DOI does not change when the object moves.")


def request(
    agent_id: str, input: Frozen | None = None, bundle: str = PERMISSIVE
) -> InvocationRequest:
    return InvocationRequest(agent_id=agent_id, policy_bundle_ref=bundle, input=input or record())

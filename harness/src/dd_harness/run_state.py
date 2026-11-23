"""One invocation as the steps of `dd_harness.pipeline` see it (docs/specs/system.md).

`RunState` is what a run was asked and what each step found; `RunHost` is what a step may read
or call of the conductor that runs it. The steps and the refusals import this module, never the
conductor, so the conductor sits above them: `Conductor` satisfies `RunHost`, as it satisfies
`ProjectEffects` for the projects.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from opentelemetry.trace import SpanContext

from dd_harness import grounding, policy
from dd_harness import sources as source_check
from dd_harness.model_grants import GrantMinter
from dd_harness.observe import Watch
from dd_harness.project_effects import ProjectEffects
from dd_harness.registry import Registered
from dd_harness.storage import RunStorage
from dd_sdk.agent import AgentResult, AgentSpec
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Delegation,
    Envelope,
    InvocationRequest,
    ModelCall,
    Principal,
    ProblemDetails,
    ToolRetrieval,
)
from dd_sdk.evidence import input_hash as compute_input_hash
from dd_sdk.tracing import Tracing

if TYPE_CHECKING:
    from dd_harness.gateway.core import Gateway, ToolGrant


@dataclass
class Grant:
    """One delegation grant, live while its parent invocation runs."""

    token: str
    parent_invocation_id: str
    parent_agent_id: str
    conversation_id: str | None
    project_id: str | None
    acting_for: Principal
    delegations: list[Delegation] = field(default_factory=list)
    # Children admitted under this grant and not yet finished; revocation waits for them.
    in_flight: int = 0
    watch: Watch = field(default_factory=lambda: Watch(None, None))  # told of each child


class RunHost(Protocol):
    """The conductor as a step sees it: the deployment's profile and stores, and the conductor's
    own bookkeeping of grants, grounding reports and spans."""

    @property
    def profile(self) -> policy.Profile: ...

    @property
    def store(self) -> RunStorage: ...

    @property
    def tracing(self) -> Tracing: ...

    @property
    def write_crate(self) -> bool: ...

    @property
    def sources(self) -> source_check.Sources: ...

    @property
    def harness_url(self) -> str | None: ...

    @property
    def projects(self) -> ProjectEffects | None: ...

    @property
    def model_grants(self) -> GrantMinter | None: ...

    @property
    def gateway(self) -> Gateway | None: ...

    def _issue_grant(
        self, request: InvocationRequest, acting_for: Principal, watch: Watch
    ) -> Grant: ...

    def _revoke_grant(self, grant: Grant) -> list[Delegation]: ...

    def _keep_report(self, invocation_id: str, report: grounding.GroundingReport) -> None: ...

    def _spans(self, trace_id: str) -> bytes: ...


@dataclass(frozen=True)
class FromProject:
    """What a run's project gives it before it starts: the classes of project content the
    conductor put into the input, why it could not fill it from the project, if it could not, and
    the pause a data steward holds on the project, if any (docs/specs/stewardship.md, invariant
    8)."""

    given: frozenset[str] = frozenset()
    unfillable: str | None = None
    paused: Mapping[str, Any] | None = None

    @property
    def given_to_run(self) -> tuple[frozenset[str], str | None, Mapping[str, Any] | None]:
        """In the order `RunState` takes them, after the link."""
        return self.given, self.unfillable, self.paused


@dataclass
class RunState:
    """One invocation as it goes through the steps: what it was asked, then what each step
    found. `given` is the classes of project content the conductor put into the input, and
    `unfillable` why it could not fill it from the project, if it could not."""

    request: InvocationRequest
    request_doc: dict[str, Any]
    acting_for: Principal
    agent: Registered
    watch: Watch
    link: SpanContext | None = None
    given: frozenset[str] = frozenset()
    unfillable: str | None = None
    # The pause a data steward holds on the run's project, if any (docs/specs/stewardship.md,
    # invariant 8).
    paused: Mapping[str, Any] | None = None
    started: datetime = field(default_factory=lambda: datetime.now(UTC))
    input_hash: str = field(init=False)
    trace_id: str = ""
    decision: policy.GateDecision | None = None
    bypasses: bool = False
    refused: tuple[str, list[str]] | None = None
    kept_back: list[str] = field(default_factory=list)
    result: AgentResult | None = None
    prob: ProblemDetails | None = None
    from_agent: bool = False
    # The agent's model calls and the prompts they name, kept whatever becomes of its result
    # (docs/specs/disclosure.md).
    model_calls: tuple[ModelCall, ...] = ()
    prompts: dict[str, dict[str, Any]] = field(default_factory=dict)
    grant: Grant | None = None
    delegations: list[Delegation] = field(default_factory=list)
    # The invocation's tool grant, and the records the gateway kept under it (docs/specs/agents.md).
    tool_grant: ToolGrant | None = None
    tool_retrievals: list[ToolRetrieval] = field(default_factory=list)
    envelope: Envelope | None = None
    doc: dict[str, Any] = field(default_factory=dict)
    report: grounding.GroundingReport | None = None
    source_report: source_check.SourceReport | None = None
    shapes_report: bytes | None = None
    # The envelope document as the agent's result made it, kept once a check or the project
    # withheld it (`pipeline.withhold`), for operators only.
    withheld: dict[str, Any] | None = None

    @property
    def spec(self) -> AgentSpec:
        return self.agent.spec

    def __post_init__(self) -> None:
        self.input_hash = compute_input_hash(self.request_doc["input"])

    @property
    def accepted(self) -> ClassSchema | None:
        """The class schema the card carries for the input, if the agent accepts its class."""
        return self.spec.accepted(str(self.request_doc["input"].get("schema_class")))

    @property
    def gate_decision(self) -> policy.GateDecision:
        assert self.decision is not None, "the gate runs first"
        return self.decision

    @property
    def finished(self) -> Envelope:
        assert self.envelope is not None, "the envelope is built inside the span"
        return self.envelope


type Step = Callable[[RunHost, RunState], None]

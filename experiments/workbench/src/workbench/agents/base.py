"""The agent interface the conductor calls.

An agent is a specification plus one method. The specification (`AgentSpec`) says what the agent
is, which input classes it accepts, what payload class it returns and which grounding contract it
declares; the conductor and the linter hold it to that. `run` decides an outcome, a payload and
the evidence it rests on. It does not fill in identifiers, timestamps or telemetry; the conductor
does, so an agent cannot mislabel its own run.

`describe(spec)` is the one manifest every consumer reads: the A2A agent card, `workbench agents`,
`GET /agents` and the shell's agent picker.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from opentelemetry.trace import Tracer

from workbench.contract.models import (
    EvidenceItem,
    Frozen,
    Grounded,
    GroundingMode,
    InvocationRequest,
    Outcome,
)


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    version: str
    description: str
    requirement_ids: tuple[str, ...]
    action_class: str  # what the policy gate matches against actions_requiring_approval
    accepts: tuple[type[Frozen], ...]  # input classes; anything else is input-not-accepted
    grounding_mode: GroundingMode
    payload_type: type[Grounded] | None  # None: the agent never succeeds with a payload
    uischema: Mapping[str, Any] | None = None  # RJSF fragment for the payload, for the shell

    def accepts_names(self) -> tuple[str, ...]:
        return tuple(t.__name__ for t in self.accepts)


def describe(spec: AgentSpec) -> dict[str, Any]:
    """The manifest entry for one agent. JSON-ready."""
    return {
        "agent_id": spec.agent_id,
        "version": spec.version,
        "description": spec.description,
        "requirement_ids": list(spec.requirement_ids),
        "action_class": spec.action_class,
        "accepts": list(spec.accepts_names()),
        "grounding_mode": spec.grounding_mode.value,
        "payload": spec.payload_type.__name__ if spec.payload_type else None,
        "uischema": dict(spec.uischema) if spec.uischema else None,
    }


@dataclass(frozen=True)
class AgentResult:
    outcome: Outcome
    payload: Grounded | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class RunContext:
    """What the conductor gives an agent besides the request.

    `input_ref` and `input_hash` are the source_id and content_hash an input_only or none agent
    cites; they are computed by the conductor so the agent cannot get them wrong.
    """

    tracer: Tracer
    input_ref: str
    input_hash: str


@runtime_checkable
class Agent(Protocol):
    spec: AgentSpec

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult: ...

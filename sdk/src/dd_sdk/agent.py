"""The agent interface.

An agent is a specification plus one method. The specification (`AgentSpec`) says what the agent
is, which input classes it accepts, what payload class it returns and which grounding contract it
declares; the workbench's conductor and linter hold it to that. `run` decides an outcome, a
payload and the evidence it rests on. It does not fill in identifiers, timestamps or telemetry;
the conductor does, so an agent cannot mislabel its own run.

An agent runs in its own process behind `dd_sdk.serve` (ADR-0011). The workbench reaches it over
A2A and sees the same `Agent` protocol through its `RemoteAgent`.

`describe(spec)` is the one manifest every consumer reads: the agent's A2A card extension, the
workbench's own agent card, `workbench agents`, `GET /agents` and the shell's agent picker.
`spec_from_description` is its inverse, used by the workbench to rebuild a spec from a card.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from opentelemetry.trace import Tracer

from dd_sdk.contract.models import (
    INPUT_TYPES,
    PAYLOAD_TYPES,
    EvidenceItem,
    Frozen,
    Grounded,
    GroundingMode,
    InvocationRequest,
    Outcome,
)

if TYPE_CHECKING:
    from dd_sdk.delegate import Delegated


class SpecError(Exception):
    """A description does not rebuild into an `AgentSpec` against this contract."""


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


DESCRIPTION_KEYS = frozenset(
    {
        "agent_id",
        "version",
        "description",
        "requirement_ids",
        "action_class",
        "accepts",
        "grounding_mode",
        "payload",
        "uischema",
    }
)


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


def spec_from_description(entry: Mapping[str, Any]) -> AgentSpec:
    """Rebuild a spec from `describe` output, resolving class names against the contract.

    A name the contract does not define is a `SpecError`: an agent cannot introduce an input or
    payload class the workbench does not know (the contract is central, ADR-0007).
    """
    missing = DESCRIPTION_KEYS - set(entry)
    if missing:
        raise SpecError(f"agent description lacks {sorted(missing)}")
    unknown_inputs = [name for name in entry["accepts"] if name not in INPUT_TYPES]
    if unknown_inputs or not entry["accepts"]:
        raise SpecError(
            f"agent {entry['agent_id']!r} accepts {unknown_inputs or 'nothing'}; the contract "
            f"defines {sorted(INPUT_TYPES)}"
        )
    payload = entry["payload"]
    if payload is not None and payload not in PAYLOAD_TYPES:
        raise SpecError(
            f"agent {entry['agent_id']!r} returns {payload!r}; the contract defines "
            f"{sorted(PAYLOAD_TYPES)}"
        )
    try:
        mode = GroundingMode(entry["grounding_mode"])
    except ValueError as exc:
        raise SpecError(f"agent {entry['agent_id']!r}: {exc}") from exc
    return AgentSpec(
        agent_id=str(entry["agent_id"]),
        version=str(entry["version"]),
        description=str(entry["description"]),
        requirement_ids=tuple(entry["requirement_ids"]),
        action_class=str(entry["action_class"]),
        accepts=tuple(INPUT_TYPES[name] for name in entry["accepts"]),
        grounding_mode=mode,
        payload_type=PAYLOAD_TYPES[payload] if payload is not None else None,
        uischema=entry["uischema"],
    )


@dataclass(frozen=True)
class AgentResult:
    outcome: Outcome
    payload: Grounded | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    # The agent's finished spans as `ReadableSpan.to_json` documents. Filled by the workbench's
    # `RemoteAgent` from the A2A response; an agent never sets it.
    spans: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class DelegationGrant:
    """Where and with what token an agent may ask the workbench to invoke another (ADR-0012).

    Issued by the conductor to an agent in grounding mode delegation, for one invocation only.
    """

    url: str
    token: str


class Delegate(Protocol):
    """Invoke another agent through the workbench and return its envelope (`dd_sdk.delegate`)."""

    def __call__(self, agent_id: str, input: Frozen) -> Delegated: ...


@dataclass(frozen=True)
class RunContext:
    """What the conductor gives an agent besides the request.

    `input_ref` and `input_hash` are the source_id and content_hash an input_only or none agent
    cites; they are computed by the conductor so the agent cannot get them wrong.

    `grant` is set by the conductor for an agent in grounding mode delegation, and forwarded by
    the workbench's `RemoteAgent`. `delegate` is what the agent calls: `dd_sdk.serve` builds it
    from the grant in the agent's process. Both are None for every other agent, and for a
    delegation agent run where the workbench has no callback address (the CLI).
    """

    tracer: Tracer
    input_ref: str
    input_hash: str
    grant: DelegationGrant | None = None
    delegate: Delegate | None = None


@runtime_checkable
class Agent(Protocol):
    spec: AgentSpec

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult: ...

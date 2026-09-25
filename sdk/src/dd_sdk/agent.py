"""The agent interface.

An agent is a specification plus one method. The specification (`AgentSpec`) says what the agent
is, which input classes it accepts, what payload class it returns and which grounding contract it
declares; the workbench's conductor and linter hold it to that. `run` decides an outcome, a
payload and the evidence it rests on. It does not fill in identifiers, timestamps or telemetry;
the conductor does, so an agent cannot mislabel its own run.

An agent runs in its own process behind `dd_sdk.serve` (ADR-0011). The workbench reaches it over
A2A and sees the same `Agent` protocol through its `RemoteAgent`.

`describe(spec)` is the one manifest every consumer reads: the agent's A2A card extension, the
workbench's own agent card, `workbench agents`, `GET /agents` and the viewer's agent picker.
`spec_from_description` is its inverse, used by the workbench to rebuild a spec from a card.
The manifest says what an agent does, never how to draw it: the viewer works out a payload's
presentation from its schema and the agent's `derivations` (ADR-0016).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import NoneType, UnionType
from typing import TYPE_CHECKING, Any, Protocol, Union, get_args, get_origin, runtime_checkable

from opentelemetry.trace import Tracer

from dd_sdk.contract.models import (
    INPUT_TYPES,
    PAYLOAD_TYPES,
    Derivation,
    EvidenceItem,
    Frozen,
    Grounded,
    GroundingMode,
    InvocationRequest,
    Outcome,
)
from dd_sdk.contract.version import CONTRACT_VERSION, compatible

if TYPE_CHECKING:
    from dd_sdk.delegate import Delegated


class SpecError(Exception):
    """A description does not rebuild into an `AgentSpec` against this contract."""


class ContractVersionError(SpecError):
    """A description declares a contract version this one cannot govern (ADR-0019)."""


@dataclass(frozen=True)
class Derived:
    """How an agent produces one payload field that it does not copy from input or evidence.

    `recorded_in` names a sibling field of type `Derivation` in which each value records how it
    actually came about, so a template fallback where a model would normally write is shown as
    template. Without it, `how` holds for every value.
    """

    how: Derivation
    recorded_in: str | None = None


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    version: str
    description: str
    action_class: str  # what the policy gate matches against actions_requiring_approval
    accepts: tuple[type[Frozen], ...]  # input classes; anything else is input-not-accepted
    grounding_mode: GroundingMode
    payload_type: type[Grounded] | None  # None: the agent never succeeds with a payload
    # Payload field path ("score", "findings.severity"; list items are transparent) -> how the
    # agent produces it. An unlisted field is copied from input or evidence.
    derivations: Mapping[str, Derived] = field(default_factory=dict)
    # The core contract the agent was built against: this SDK's, or the one its card declares.
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        for path, derived in self.derivations.items():
            _check_derivation(self, path, derived)

    def accepts_names(self) -> tuple[str, ...]:
        return tuple(t.__name__ for t in self.accepts)


DESCRIPTION_KEYS = frozenset(
    {
        "agent_id",
        "version",
        "description",
        "action_class",
        "accepts",
        "grounding_mode",
        "payload",
        "derivations",
        "contract_version",
    }
)


def _field_model(annotation: Any) -> type[Frozen] | None:
    """The model a field holds, directly, in a list or as an optional; None for a scalar."""
    if isinstance(annotation, type) and issubclass(annotation, Frozen):
        return annotation
    if get_origin(annotation) in (list, Union, UnionType):
        for arg in get_args(annotation):
            if arg is not NoneType and (found := _field_model(arg)) is not None:
                return found
    return None


def _is_derivation(annotation: Any) -> bool:
    if annotation is Derivation:
        return True
    return get_origin(annotation) in (Union, UnionType) and Derivation in get_args(annotation)


def _check_derivation(spec: AgentSpec, path: str, derived: Derived) -> None:
    where = f"agent {spec.agent_id!r} derivation {path!r}"
    if spec.payload_type is None:
        raise SpecError(f"{where}: the agent declares no payload")
    if not isinstance(derived.how, Derivation):
        raise SpecError(f"{where}: {derived.how!r} is not a Derivation")
    *parents, name = path.split(".")
    model: type[Frozen] = spec.payload_type
    for part in parents:
        info = model.model_fields.get(part)
        nested = _field_model(info.annotation) if info else None
        if nested is None:
            raise SpecError(f"{where}: {model.__name__} has no nested field {part!r}")
        model = nested
    if name not in model.model_fields:
        raise SpecError(f"{where}: {model.__name__} has no field {name!r}")
    if derived.recorded_in is not None:
        recorder = model.model_fields.get(derived.recorded_in)
        if recorder is None or not _is_derivation(recorder.annotation):
            raise SpecError(
                f"{where}: {model.__name__}.{derived.recorded_in} is not a Derivation field"
            )


def describe(spec: AgentSpec) -> dict[str, Any]:
    """The manifest entry for one agent. JSON-ready."""
    return {
        "agent_id": spec.agent_id,
        "version": spec.version,
        "description": spec.description,
        "action_class": spec.action_class,
        "accepts": list(spec.accepts_names()),
        "grounding_mode": spec.grounding_mode.value,
        "payload": spec.payload_type.__name__ if spec.payload_type else None,
        "derivations": {
            path: {"how": d.how.value, "recorded_in": d.recorded_in}
            for path, d in spec.derivations.items()
        },
        "contract_version": spec.contract_version,
    }


def spec_from_description(entry: Mapping[str, Any]) -> AgentSpec:
    """Rebuild a spec from `describe` output, resolving class names against the contract.

    A name the contract does not define is a `SpecError`: an agent cannot introduce an input or
    payload class the workbench does not know (the contract is central, ADR-0007).

    A description built against a contract this one cannot govern is a `ContractVersionError`,
    checked first, since under another contract the rest of the description may not parse.
    """
    declared = entry.get("contract_version")
    if not isinstance(declared, str):
        raise ContractVersionError(
            f"agent {entry.get('agent_id')!r} declares no contract version; this workbench "
            f"governs contract {CONTRACT_VERSION}"
        )
    if not compatible(declared):
        raise ContractVersionError(
            f"agent {entry.get('agent_id')!r} was built against contract {declared}; this "
            f"workbench governs contract {CONTRACT_VERSION}"
        )
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
    try:
        derivations = {
            str(path): Derived(Derivation(d["how"]), d.get("recorded_in"))
            for path, d in entry["derivations"].items()
        }
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise SpecError(f"agent {entry['agent_id']!r}: malformed derivations: {exc}") from exc
    return AgentSpec(
        agent_id=str(entry["agent_id"]),
        version=str(entry["version"]),
        description=str(entry["description"]),
        action_class=str(entry["action_class"]),
        accepts=tuple(INPUT_TYPES[name] for name in entry["accepts"]),
        grounding_mode=mode,
        payload_type=PAYLOAD_TYPES[payload] if payload is not None else None,
        derivations=derivations,
        contract_version=declared,
    )


@dataclass(frozen=True)
class AgentResult:
    outcome: Outcome
    payload: Grounded | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class Delegate(Protocol):
    """Invoke another agent through the workbench and return its envelope (`dd_sdk.delegate`)."""

    def __call__(self, agent_id: str, input: Frozen) -> Delegated: ...


@dataclass(frozen=True)
class RunContext:
    """What the conductor gives an agent besides the request.

    `input_ref` and `input_hash` are the source_id and content_hash an input_only or none agent
    cites; they are computed by the conductor so the agent cannot get them wrong.

    `delegate` is what an agent in grounding mode delegation calls to invoke another agent.
    `dd_sdk.serve` binds it to the grant the workbench sent with the request (ADR-0012). It is
    None for every other agent, and for a delegation agent run where the workbench has no
    callback address (the CLI).
    """

    tracer: Tracer
    input_ref: str
    input_hash: str
    delegate: Delegate | None = None


@runtime_checkable
class Agent(Protocol):
    spec: AgentSpec

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult: ...

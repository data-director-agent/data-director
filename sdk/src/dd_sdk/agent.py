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

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from opentelemetry.trace import Tracer

from dd_sdk.contract.classes import ClassSchema, ClassSchemaError
from dd_sdk.contract.models import (
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
    requirement_ids: tuple[str, ...]
    action_class: str  # what the policy gate matches against actions_requiring_approval
    accepts: tuple[ClassSchema, ...]  # input classes; anything else is input-not-accepted
    grounding_mode: GroundingMode
    payload: ClassSchema | None  # None: the agent never succeeds with a payload
    # Payload field path ("score", "findings.severity"; list items are transparent) -> how the
    # agent produces it. An unlisted field is copied from input or evidence.
    derivations: Mapping[str, Derived] = field(default_factory=dict)
    # The core contract the agent was built against: this SDK's, or the one its card declares.
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.payload is not None and not self.payload.grounded:
            raise SpecError(
                f"agent {self.agent_id!r}: payload class {self.payload.name} does not mix in "
                "Grounded (its schema does not require grounded_on)"
            )
        for path, derived in self.derivations.items():
            _check_derivation(self, path, derived)

    def accepts_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.accepts)

    def accepted(self, schema_class: str) -> ClassSchema | None:
        """The accepted input class named `schema_class`, or None if the agent does not read it."""
        return next((c for c in self.accepts if c.name == schema_class), None)

    def schemas(self) -> Iterator[ClassSchema]:
        """Every class the agent reads or returns: what its card carries."""
        yield from self.accepts
        if self.payload is not None:
            yield self.payload


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
        "derivations",
        "contract_version",
        "schemas",
    }
)
DERIVATION_REF = "#/$defs/Derivation"


def _resolve(schema: Mapping[str, Any], node: Mapping[str, Any]) -> Mapping[str, Any]:
    """Follow `$ref` into the class schema's `$defs`, a list into its items, and an optional
    (`anyOf` with null) into the arm that is not null."""
    while True:
        ref = node.get("$ref")
        arms = [a for a in node.get("anyOf", ()) if a.get("type") != "null"]
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            node = schema.get("$defs", {}).get(ref.removeprefix("#/$defs/"), {})
        elif "items" in node:
            node = node["items"]
        elif len(arms) == 1:
            node = arms[0]
        else:
            return node


def _is_derivation(node: Mapping[str, Any]) -> bool:
    if node.get("$ref") == DERIVATION_REF:
        return True
    return any(_is_derivation(arm) for arm in node.get("anyOf", ()))


def _check_derivation(spec: AgentSpec, path: str, derived: Derived) -> None:
    """A derivation names a field of the payload class's schema; `recorded_in` a Derivation."""
    where = f"agent {spec.agent_id!r} derivation {path!r}"
    if spec.payload is None:
        raise SpecError(f"{where}: the agent declares no payload")
    if not isinstance(derived.how, Derivation):
        raise SpecError(f"{where}: {derived.how!r} is not a Derivation")
    schema = spec.payload.json_schema
    *parents, name = path.split(".")
    node: Mapping[str, Any] = schema
    holder = spec.payload.name
    for part in parents:
        nested = _resolve(schema, node.get("properties", {}).get(part, {}))
        if "properties" not in nested:
            raise SpecError(f"{where}: {holder} has no nested field {part!r}")
        node, holder = nested, str(nested.get("title", part))
    properties = node.get("properties", {})
    if name not in properties:
        raise SpecError(f"{where}: {holder} has no field {name!r}")
    if derived.recorded_in is not None:
        recorder = properties.get(derived.recorded_in)
        if recorder is None or not _is_derivation(recorder):
            raise SpecError(f"{where}: {holder}.{derived.recorded_in} is not a Derivation field")


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
        "payload": spec.payload.name if spec.payload else None,
        "derivations": {
            path: {"how": d.how.value, "recorded_in": d.recorded_in}
            for path, d in spec.derivations.items()
        },
        "contract_version": spec.contract_version,
        "schemas": {c.name: c.describe() for c in spec.schemas()},
    }


def spec_from_description(entry: Mapping[str, Any]) -> AgentSpec:
    """Rebuild a spec from `describe` output, with its classes known only by their schemas.

    A description built against a contract this one cannot govern is a `ContractVersionError`,
    checked first, since under another contract the rest of the description may not parse. A
    class without a schema, a schema that does not match its digest or does not designate its
    class, and a payload class that does not mix in `Grounded` are each a `SpecError`
    (ADR-0019). No class needs to be known in advance.
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
    agent_id = str(entry["agent_id"])
    if not entry["accepts"]:
        raise SpecError(f"agent {agent_id!r} accepts nothing")
    schemas = entry["schemas"] if isinstance(entry["schemas"], Mapping) else {}

    def rebuild(name: str) -> ClassSchema:
        if name not in schemas:
            raise SpecError(f"agent {agent_id!r} names class {name!r} but carries no schema for it")
        try:
            return ClassSchema.from_description(name, schemas[name])
        except ClassSchemaError as exc:
            raise SpecError(f"agent {agent_id!r}: {exc}") from exc

    accepts = tuple(rebuild(str(name)) for name in entry["accepts"])
    payload = rebuild(str(entry["payload"])) if entry["payload"] is not None else None
    try:
        mode = GroundingMode(entry["grounding_mode"])
    except ValueError as exc:
        raise SpecError(f"agent {agent_id!r}: {exc}") from exc
    try:
        derivations = {
            str(path): Derived(Derivation(d["how"]), d.get("recorded_in"))
            for path, d in entry["derivations"].items()
        }
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise SpecError(f"agent {agent_id!r}: malformed derivations: {exc}") from exc
    return AgentSpec(
        agent_id=agent_id,
        version=str(entry["version"]),
        description=str(entry["description"]),
        requirement_ids=tuple(entry["requirement_ids"]),
        action_class=str(entry["action_class"]),
        accepts=accepts,
        grounding_mode=mode,
        payload=payload,
        derivations=derivations,
        contract_version=declared,
    )


def typed_request(spec: AgentSpec, request: InvocationRequest) -> InvocationRequest:
    """The request with its input parsed into the agent's own model, where the agent has one.

    What an agent's `run` is given: `dd_sdk.serve` and the conductor's in-process path both call
    it once the input has been checked against its class schema. An input of a class the agent
    does not accept, or one it holds no model for, is left as it is.
    """
    schema_class = getattr(request.input, "schema_class", None)
    accepted = spec.accepted(schema_class) if isinstance(schema_class, str) else None
    if accepted is None or accepted.model is None or isinstance(request.input, accepted.model):
        return request
    document = request.input.model_dump(mode="json", exclude_none=True)
    return request.model_copy(update={"input": accepted.parse_input(document)})


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

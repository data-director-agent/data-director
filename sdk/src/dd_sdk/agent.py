"""The agent interface.

An agent is a specification plus one method. The specification (`AgentSpec`) says what the agent
is, which input classes it accepts, what payload class it returns and which grounding contract it
declares; the harness's conductor and linter hold it to that. `run` decides an outcome, a
payload and the evidence it rests on. It does not fill in identifiers, timestamps or telemetry;
the conductor does, so an agent cannot mislabel its own run.

An agent runs in its own process behind `dd_sdk.serve` (docs/specs/agents.md). The harness reaches
it over A2A and sees the same `Agent` protocol through its `RemoteAgent`.

`describe(spec)` is the one manifest every consumer reads: the agent's A2A card extension, the
harness's own agent card, `workbench agents`, `GET /agents` and the viewer's agent picker.
`spec_from_description` is its inverse, used by the harness to rebuild a spec from a card.
The manifest says what an agent does, never how to draw it: the viewer works out a payload's
presentation from its schema and the agent's `derivations` (docs/specs/agents.md).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from opentelemetry.trace import Tracer

from dd_sdk.agent_checks import Derived as Derived
from dd_sdk.agent_checks import Setting as Setting
from dd_sdk.agent_checks import SpecError as SpecError
from dd_sdk.agent_checks import check_derivation, check_icon, check_setting
from dd_sdk.agent_result import AgentResult as AgentResult
from dd_sdk.contract.classes import ClassSchema, ClassSchemaError
from dd_sdk.contract.models import (
    Derivation,
    EvidenceItem,
    Frozen,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)
from dd_sdk.contract.version import CONTRACT_VERSION, compatible
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION
from dd_sdk.process_flow import OUT_OF_SCOPE, PERSON_DECIDES, STEPS
from dd_sdk.skills import SkillUse, skills_from_description
from dd_sdk.tools import Tools, ToolUse, tools_from_description

if TYPE_CHECKING:
    from dd_sdk.delegate import Delegated


class ContractVersionError(SpecError):
    """A description declares a contract version this one cannot govern (docs/specs/contract.md)."""


@dataclass(frozen=True)
class ModelUse:
    """A model the agent sends data to, as configured: who provides it, which model, and whether
    it runs on the provider's service (`hosted`) or on the institution's own (`local`)
    (docs/specs/policy-and-identity.md). It names no credential. `tools` says the agent relies on
    the model to call tools, so a profile's model map never routes it to a model that does not
    serve them (docs/specs/model-accounts.md, The model map)."""

    provider: str
    model: str
    hosting: Literal["hosted", "local"]
    tools: bool = False


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    version: str
    description: str
    action_class: str  # what the policy gate matches against actions_requiring_approval
    accepts: tuple[ClassSchema, ...]  # input classes; anything else is input-not-accepted
    grounding_mode: GroundingMode
    payload: ClassSchema | None  # None: the agent never succeeds with a payload
    # Payload field path ("score", "findings.severity"; list items are transparent) -> how the
    # agent produces it. An unlisted field is copied from input or evidence.
    derivations: Mapping[str, Derived] = field(default_factory=dict)
    # The core contract the agent was built against: this SDK's, or the one its card declares.
    contract_version: str = CONTRACT_VERSION
    # The models the agent sends data to, as configured. Empty: it calls no model.
    models: tuple[ModelUse, ...] = ()
    # The process flow's step ids ("governance.policies") the agent serves, so an orchestrator can
    # place it in the flow (`dd_sdk.process_flow`, docs/specs/orchestration.md). The requirements it
    # bears on follow from the steps; whether it meets them is for the requirements register. Empty:
    # none.
    serves: tuple[str, ...] = ()
    # The persona's name as a researcher sees it ("Metadata Librarian", docs/specs/agents.md).
    # Empty: the app and the orchestrators show `agent_id` instead.
    title: str = ""
    # The persona's icon: one emoji shown beside its title (docs/specs/agents.md). Empty: clients
    # show their default.
    icon: str = ""
    # The options a deployment's profile may set, by name (docs/specs/policy-and-identity.md).
    # Empty: the agent offers none, and a profile that sets one for it is refused at invocation.
    settings: Mapping[str, Setting] = field(default_factory=dict)
    # The Agent Skills it may load into its system prompt, each pinned by version and digest
    # (`dd_sdk.skills`, docs/specs/agents.md). Empty: it loads none.
    skills: tuple[SkillUse, ...] = ()
    # The MCP servers and tools it calls through the harness's tool gateway (`dd_sdk.tools`,
    # docs/specs/agents.md). The profile grants servers; a call to one not declared here is
    # refused. Empty: it calls none.
    tools: tuple[ToolUse, ...] = ()

    def __post_init__(self) -> None:
        unknown = sorted(set(self.serves) - STEPS)
        if unknown:
            raise SpecError(
                f"agent {self.agent_id!r} serves {unknown}, which are not process flow steps; "
                "name steps such as 'deposit.validate', and the requirements follow from them"
            )
        out = sorted(set(self.serves) & OUT_OF_SCOPE)
        if out:
            raise SpecError(
                f"agent {self.agent_id!r} serves {out}, which are out of scope for now "
                "(docs/specs/orchestration.md); no agent may serve them"
            )
        decided = sorted(set(self.serves) & PERSON_DECIDES)
        if decided:
            raise SpecError(
                f"agent {self.agent_id!r} serves {decided}, which a person decides (C2, "
                "docs/specs/agents.md); no agent may serve them"
            )
        if self.payload is not None and not self.payload.grounded:
            raise SpecError(
                f"agent {self.agent_id!r}: payload class {self.payload.name} does not mix in "
                "Grounded (its schema does not require grounded_on)"
            )
        for path, derived in self.derivations.items():
            check_derivation(self.agent_id, self.payload, path, derived)
        for name, setting in self.settings.items():
            check_setting(self.agent_id, name, setting)
        names = [s.name for s in self.skills]
        if len(set(names)) != len(names):
            raise SpecError(f"agent {self.agent_id!r} declares a skill twice: {sorted(names)}")
        servers = [t.server for t in self.tools]
        if len(set(servers)) != len(servers):
            raise SpecError(f"agent {self.agent_id!r} declares a tool server twice")
        check_icon(self.agent_id, self.icon)

    def default_settings(self) -> dict[str, str]:
        """Each setting's default: what applies where the profile sets none."""
        return {name: s.default for name, s in self.settings.items()}

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
        "action_class",
        "accepts",
        "grounding_mode",
        "payload",
        "derivations",
        "contract_version",
        "schemas",
    }
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
        "payload": spec.payload.name if spec.payload else None,
        "derivations": {
            path: {"how": d.how.value, "recorded_in": d.recorded_in}
            for path, d in spec.derivations.items()
        },
        "contract_version": spec.contract_version,
        "models": [_model_use(m) for m in spec.models],
        "serves": list(spec.serves),
        "title": spec.title,
        "icon": spec.icon,
        "settings": {
            name: {
                "choices": list(s.choices),
                "default": s.default,
                "description": s.description,
            }
            for name, s in spec.settings.items()
        },
        "skills": [s.describe() for s in spec.skills],
        "tools": [t.describe() for t in spec.tools],
        "schemas": {c.name: c.describe() for c in spec.schemas()},
    }


def spec_from_description(entry: Mapping[str, Any]) -> AgentSpec:
    """Rebuild a spec from `describe` output, with its classes known only by their schemas.

    A description built against a contract this one cannot govern is a `ContractVersionError`,
    checked first, since under another contract the rest of the description may not parse. A
    class without a schema, a schema that does not match its digest or does not designate its
    class, and a payload class that does not mix in `Grounded` are each a `SpecError`
    (docs/specs/contract.md). No class needs to be known in advance.
    """
    declared = _contract_version(entry)
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
    models = _models(agent_id, entry)
    # `serves` may be absent: a card written before docs/specs/orchestration.md serves no
    # requirement.
    serves = entry.get("serves", ())
    if not isinstance(serves, list | tuple):
        raise SpecError(f"agent {agent_id!r}: serves is not a list")
    title, icon = _persona(agent_id, entry)
    # `settings` may be absent: a card written before docs/specs/policy-and-identity.md offers none.
    try:
        settings = {
            str(name): Setting(
                tuple(str(c) for c in s["choices"]),
                str(s["default"]),
                str(s.get("description") or ""),
            )
            for name, s in (entry.get("settings") or {}).items()
        }
    except (AttributeError, KeyError, TypeError) as exc:
        raise SpecError(f"agent {agent_id!r}: malformed settings: {exc}") from exc
    try:
        skills = skills_from_description(agent_id, entry)
        tools = tools_from_description(agent_id, entry)
    except ValueError as exc:
        raise SpecError(str(exc)) from exc
    return AgentSpec(
        agent_id=agent_id,
        version=str(entry["version"]),
        description=str(entry["description"]),
        action_class=str(entry["action_class"]),
        accepts=accepts,
        grounding_mode=mode,
        payload=payload,
        derivations=derivations,
        contract_version=declared,
        models=models,
        serves=tuple(str(r) for r in serves),
        title=title,
        icon=icon,
        settings=settings,
        skills=skills,
        tools=tools,
    )


def _persona(agent_id: str, entry: Mapping[str, Any]) -> tuple[str, str]:
    """The persona's title and icon. Either may be absent: a card written before
    docs/specs/agents.md names no persona, and one written before icons has none."""
    title = entry.get("title") or ""
    if not isinstance(title, str):
        raise SpecError(f"agent {agent_id!r}: title is not a string")
    icon = entry.get("icon") or ""
    if not isinstance(icon, str):
        raise SpecError(f"agent {agent_id!r}: icon is not a string")
    return title, icon


def _contract_version(entry: Mapping[str, Any]) -> str:
    """The contract version `entry` declares, or a `ContractVersionError` if this one cannot
    govern it."""
    declared = entry.get("contract_version")
    if not isinstance(declared, str):
        raise ContractVersionError(
            f"agent {entry.get('agent_id')!r} declares no contract version; this harness "
            f"governs contract {CONTRACT_VERSION}"
        )
    if not compatible(declared):
        raise ContractVersionError(
            f"agent {entry.get('agent_id')!r} was built against contract {declared}; this "
            f"harness governs contract {CONTRACT_VERSION}"
        )
    return declared


def _models(agent_id: str, entry: Mapping[str, Any]) -> tuple[ModelUse, ...]:
    """The models `entry` declares. They may be absent: a card written before
    docs/specs/policy-and-identity.md declares no model."""
    try:
        return tuple(
            ModelUse(
                str(m["provider"]),
                str(m["model"]),
                _hosting(m["hosting"]),
                _tools(m.get("tools", False)),
            )
            for m in entry.get("models", ())
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SpecError(f"agent {agent_id!r}: malformed models: {exc}") from exc


def _hosting(value: object) -> Literal["hosted", "local"]:
    if value == "hosted" or value == "local":
        return value
    raise ValueError(f"hosting {value!r}: expected hosted or local")


def _tools(value: object) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"tools {value!r}: expected true or false")


def _model_use(use: ModelUse) -> dict[str, Any]:
    # `tools` is written only when true, so a card that relies on no tool calls reads as before.
    described: dict[str, Any] = {
        "provider": use.provider,
        "model": use.model,
        "hosting": use.hosting,
    }
    if use.tools:
        described["tools"] = True
    return described


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


class Delegate(Protocol):
    """Invoke another agent through the harness and return its envelope (`dd_sdk.delegate`).

    `manifest` is what the harness says it may invoke: one `describe(spec)` per registered agent,
    schemas included. A delegation agent routes from it, never from its own list
    (docs/specs/orchestration.md).
    """

    def __call__(self, agent_id: str, input: Frozen) -> Delegated: ...

    def manifest(self) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class RunContext:
    """What the conductor gives an agent besides the request.

    `input_ref` and `input_hash` are the source_id and content_hash an input_only or none agent
    cites; they are computed by the conductor so the agent cannot get them wrong.

    `delegate` is what an agent in grounding mode delegation calls to invoke another agent.
    `dd_sdk.serve` binds it to the grant the harness sent with the request
    (docs/specs/orchestration.md). It is None for every other agent, and for a delegation agent run
    where the harness has no callback address (the CLI).

    `settings` are the agent's settings for this invocation: the defaults its card declares,
    overlaid by the profile's `agent_settings` (docs/specs/policy-and-identity.md). An agent reads
    a setting with `setting(ctx, spec, name)`, which falls back to the card's default where the
    caller sent none, as a test or the CLI may not.

    `model_grant` is the model grant the conductor minted for this invocation, if the agent's card
    declares `models` and the harness is configured to mint one (docs/specs/model-accounts.md). It
    is opaque: the agent never parses it, and the SDK's model adapters send it to the broker with
    each call (`dd_sdk.model.bind_grant`).

    `tools` calls the MCP tools the profile grants the agent, through the harness's tool gateway
    (`dd_sdk.tools`, docs/specs/agents.md). `dd_sdk.serve` binds it to the grant the harness sent;
    it is None where the agent is granted no server or the harness has no gateway.
    """

    tracer: Tracer
    input_ref: str
    input_hash: str
    delegate: Delegate | None = None
    model_grant: str | None = None
    settings: Mapping[str, str] = field(default_factory=dict)
    tools: Tools | None = None


def setting(ctx: RunContext, spec: AgentSpec, name: str) -> str:
    """The value of one of the agent's own settings for this invocation: what the conductor sent,
    or the card's default. A name the card does not declare is a programmer error."""
    declared = spec.settings.get(name)
    if declared is None:
        raise KeyError(f"agent {spec.agent_id!r} declares no setting {name!r}")
    sent = ctx.settings.get(name)
    return sent if sent in declared.choices else declared.default


# The agent kit: what every agent's `run` builds, written once. An agent may not import another
# agent, so what they share lives here (docs/architecture-review.md, finding 4).


def abstain(reason: ReasonCode, statement: str) -> AgentResult:
    """An abstention: the agent declines to answer, with no payload and no evidence."""
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.ABSTAINED, reason_code=reason, statement=statement)
    )


def input_ref(ctx: RunContext) -> GroundingRef:
    """The grounding reference to this invocation's input, as an input_only or none agent cites."""
    return GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)


def input_evidence(ctx: RunContext, *, retrieved_at: datetime | None = None) -> EvidenceItem:
    """The evidence item for this invocation's input, which `input_ref(ctx)` points at.

    `retrieved_at` defaults to now; pass it to pin the time.
    """
    return EvidenceItem(
        source_id=ctx.input_ref,
        retrieved_at=retrieved_at if retrieved_at is not None else datetime.now(UTC),
        hash_algorithm=HASH_ALGORITHM,
        canonicalisation=INPUT_CANONICALISATION,
        content_hash=ctx.input_hash,
    )


@runtime_checkable
class Agent(Protocol):
    spec: AgentSpec

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult: ...

"""The steps of one invocation, in order, over a `RunState` (docs/specs/system.md).

`Conductor._run` runs `INSIDE_SPAN` within the run's `invoke_agent` span and `AFTER_SPAN` once it
has ended, so the grounding linter reads the finished tree. Each step is a function of the
conductor and the run, and reads and fills the run's state; only the conductor calls them, so what
they fill (identifiers, timestamps, telemetry, grounding mode, input hash, lineage) is still the
conductor's to fill.

Before the agent runs, the first of `REFUSALS` that applies decides the run without it: the
policy gate, the model broker, approval, cancellation, the input check, the project's facts and
the profile's `hosted_models`, in that order. After it, a violation of the grounding linter or the
source check withholds a succeeded result, a result that breaks the contract fails as the agent's
error, and the project takes the run's effects (`dd_harness.project_effects`), a draft it refuses
failing the run. The shape check only reports.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from opentelemetry.trace import SpanContext

from dd_harness import grounding, policy, shacl
from dd_harness import observe as steps
from dd_harness import sources as source_check
from dd_harness.observe import Watch, cancelled_result
from dd_harness.provenance import process_run_crate
from dd_harness.registry import Registered
from dd_harness.remote import Received, RemoteAgent
from dd_harness.storage import CRATE, GROUNDING, SOURCES, SPANS, VALIDATION
from dd_sdk.agent import AgentResult, AgentSpec, RunContext, typed_request
from dd_sdk.contract import problem as problems
from dd_sdk.contract import validate
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Delegation,
    Envelope,
    GroundingMode,
    InvocationRequest,
    ModelCall,
    Outcome,
    OutcomeStatus,
    Principal,
    ProblemDetails,
    ReasonCode,
    Telemetry,
    input_source_id,
    to_document,
)
from dd_sdk.contract.version import CONTRACT_VERSION
from dd_sdk.delegate import DelegationGrant
from dd_sdk.evidence import input_hash as compute_input_hash
from dd_sdk.model_account import accounted
from dd_sdk.prompts import prompt_digest
from dd_sdk.security_log import SecurityEvent, emit
from dd_sdk.tracing import policy_gate_span

if TYPE_CHECKING:
    from dd_harness.conductor import Conductor, Grant

DATA_STEWARD = "data_steward"

type Decided = tuple[AgentResult, ProblemDetails | None]


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
    envelope: Envelope | None = None
    doc: dict[str, Any] = field(default_factory=dict)
    report: grounding.GroundingReport | None = None
    source_report: source_check.SourceReport | None = None
    shapes_report: bytes | None = None

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


type Step = Callable[[Conductor, RunState], None]


# 1. Policy gate, against the deployment's profile.
def gate(conductor: Conductor, run: RunState) -> None:
    """The policy gate, and who pays: with own accounts on, only an agent the operator states
    calls through the model broker may call a model (docs/specs/model-accounts.md, invariant
    14)."""
    spec = run.spec
    run.watch.started(steps.GATE)
    with policy_gate_span(conductor.tracing.tracer, spec.agent_id):
        run.decision = policy.gate(
            conductor.profile, spec.agent_id, spec.action_class, spec.settings
        )
    run.watch.finished(steps.GATE)
    run.bypasses = run.decision.allowed and conductor._bypasses_broker(run.agent)


# 2-4. The input check.
def check_input(conductor: Conductor, run: RunState) -> None:
    """The input against the agent's card, the project's facts and what the profile keeps from
    hosted models. Run only for an agent the gate lets run straight away, and not once the run is
    cancelled."""
    decision = run.gate_decision
    if not decision.allowed or run.bypasses or decision.requires_approval or run.watch.cancelled():
        return
    run.watch.started(steps.INPUT)
    run.refused = _input_refusal(run.spec, run.request_doc["input"])
    if run.refused is None and run.unfillable is None:
        hostings = (model.hosting for model in run.spec.models)
        run.kept_back = policy.withheld(conductor.profile, hostings, run.given)
    run.watch.finished(steps.INPUT)


def refuse(conductor: Conductor, run: RunState) -> None:
    """Decide the run without its agent, by the first of `REFUSALS` that applies."""
    for refusal in REFUSALS:
        if (decided := refusal(conductor, run)) is not None:
            run.result, run.prob = decided
            return


def _failed(statement: str) -> AgentResult:
    return AgentResult(outcome=Outcome(status=OutcomeStatus.FAILED, statement=statement))


def _not_allowed(conductor: Conductor, run: RunState) -> Decided | None:
    decision, spec, profile = run.gate_decision, run.spec, conductor.profile
    if decision.allowed:
        return None
    if decision.refusal == "action-class-mismatch":
        prob = problems.action_class_mismatch(
            spec.agent_id, spec.action_class, profile.agents[spec.agent_id], profile.profile_id
        )
    elif decision.refusal == "setting-not-declared":
        prob = problems.setting_not_declared(spec.agent_id, decision.reason, profile.profile_id)
    else:
        prob = problems.agent_not_permitted(spec.agent_id, profile.profile_id)
    return _failed(f"{decision.reason}. The agent was not run."), prob


def _broker_bypassed(conductor: Conductor, run: RunState) -> Decided | None:
    """Refused before a steward is asked to approve it: approval cannot make the deployment's
    configuration honour the profile."""
    if not run.bypasses:
        return None
    agent_id, profile_id = run.spec.agent_id, conductor.profile.profile_id
    emit(
        SecurityEvent.BROKER_BYPASS_REFUSED,
        outcome="failure",
        service="harness",
        principal=run.acting_for.principal_id,
        reason="model-broker-bypassed",
        agent_id=agent_id,
        invocation_id=run.request.invocation_id,
        profile_id=profile_id,
    )
    statement = (
        f"{agent_id} calls a model, profile {profile_id!r} lets "
        "people's own model accounts pay, and the agent configuration does "
        "not state that it calls through the model broker. The agent was not "
        "run."
    )
    return _failed(statement), problems.model_broker_bypassed(agent_id, profile_id)


def _needs_approval(conductor: Conductor, run: RunState) -> Decided | None:
    decision = run.gate_decision
    if not decision.requires_approval:
        return None
    outcome = Outcome(
        status=OutcomeStatus.REFERRED,
        reason_code=ReasonCode.POLICY_REQUIRES_APPROVAL,
        referred_to=DATA_STEWARD,
        statement=f"{decision.reason}. The agent was not run.",
    )
    return AgentResult(outcome=outcome), None


def _cancelled(conductor: Conductor, run: RunState) -> Decided | None:
    return cancelled_result(run.spec.agent_id, ran=False) if run.watch.cancelled() else None


def _input_refused(conductor: Conductor, run: RunState) -> Decided | None:
    """2. Input check, against the class schema the agent's card carries (docs/specs/contract.md).
    A valid request addressed to an agent that does not read this input is an outcome, not an
    exception: the caller, the store and a reviewer all see the refusal as an envelope, as they
    do a policy refusal."""
    if not run.refused:
        return None
    spec = run.spec
    got, errors = run.refused
    statement = (
        f"The input is not a valid {got}: {'; '.join(errors)}."
        if errors
        else f"{spec.agent_id} accepts {', '.join(spec.accepts_names())}, not {got}."
    )
    prob = problems.input_not_accepted(spec.agent_id, got, spec.accepts_names(), tuple(errors))
    return _failed(f"{statement} The agent was not run."), prob


def _unfillable(conductor: Conductor, run: RunState) -> Decided | None:
    """3. Project facts: the document a redraft names must be one of the project's, of the kind
    asked for (docs/specs/projects.md, invariant 6)."""
    if run.unfillable is None:
        return None
    statement = f"{run.unfillable}. The agent was not run."
    return _failed(statement), problems.revision_refused(run.unfillable)


def _kept_back(conductor: Conductor, run: RunState) -> Decided | None:
    """4. Project content, against the profile's `hosted_models` (docs/specs/projects.md,
    invariant 8): nothing is sent that the profile does not let an agent calling a hosted model
    see."""
    if not run.kept_back:
        return None
    agent_id, profile_id = run.spec.agent_id, conductor.profile.profile_id
    statement = (
        f"{agent_id} calls a hosted model, and profile "
        f"{profile_id!r} does not let one be given the project's "
        f"{' or '.join(run.kept_back)}. The agent was not run."
    )
    prob = problems.project_content_withheld(agent_id, tuple(run.kept_back), profile_id)
    return _failed(statement), prob


# In order: the first that applies decides the run, and its agent is not run.
REFUSALS: tuple[Callable[[Conductor, RunState], Decided | None], ...] = (
    _not_allowed,
    _broker_bypassed,
    _needs_approval,
    _cancelled,
    _input_refused,
    _unfillable,
    _kept_back,
)


# 5. Run the agent. An exception becomes a failed outcome; never a crash.
def invoke_agent(conductor: Conductor, run: RunState) -> None:
    """Run the agent, unless a refusal decided the run. A run cancelled while its agent worked
    ends here: a blocking call cannot be stopped, so what the agent answered is discarded, and
    its model calls are kept."""
    if run.result is not None:
        return
    spec, agent, request = run.spec, run.agent, run.request
    # A grant travels on the A2A wire, so only a remote agent can be sent one.
    sent_grant: DelegationGrant | None = None
    if (
        spec.grounding_mode == GroundingMode.DELEGATION
        and request.parent_invocation_id is None
        and conductor.harness_url is not None
        and isinstance(agent, RemoteAgent)
    ):
        run.grant = conductor._issue_grant(request, run.acting_for, run.watch)
        sent_grant = DelegationGrant(url=conductor.harness_url, token=run.grant.token)
    model_grant = conductor._model_grant(agent, request, run.acting_for)
    ctx = RunContext(
        tracer=conductor.tracing.tracer,
        input_ref=input_source_id(request.invocation_id),
        input_hash=run.input_hash,
        settings=run.gate_decision.settings,
    )
    # The agent is never told which project it works in (docs/specs/projects.md).
    sent = request.model_copy(update={"project_id": None})
    run.watch.started(steps.AGENT)
    try:
        # An in-process agent records its spans in this trace already. Like a served one, it
        # ends abstained if a person's own model account is refused.
        received = (
            agent.call(sent, ctx, sent_grant, model_grant=model_grant)
            if isinstance(agent, RemoteAgent)
            else Received(accounted(lambda: agent.run(typed_request(spec, sent), ctx)))
        )
    except Exception as exc:  # noqa: BLE001 — converted to a failed outcome by design
        run.result = _failed(f"Agent raised: {exc}")
        run.prob = problems.agent_error(spec.agent_id, exc)
    else:
        _received(conductor, run, received)
    run.watch.finished(steps.AGENT)
    if run.watch.cancelled():
        run.result, run.prob = cancelled_result(spec.agent_id, ran=True)
        run.from_agent = False


def _received(conductor: Conductor, run: RunState, received: Received) -> None:
    """Take what the agent answered. An agent that returns a payload other than the class it
    declared, or one its own class schema does not admit, or prompts that are not those its
    calls name, is contradicting its specification: a programmer error, handled the same way as
    an exception."""
    spec = run.spec
    run.from_agent = True
    # A remote agent's spans were recorded in its own process; bring them into this trace so the
    # linter reads one tree (docs/specs/agents.md).
    conductor.tracing.import_spans(run.trace_id, received.spans)
    result = run.result = received.result
    run.model_calls = result.model_calls
    run.prompts, unmatched = _matched_prompts(result)
    mismatch: Exception | None = (
        ValueError(unmatched)
        if unmatched
        else _payload_mismatch(spec, to_document(result.payload))
        if result.payload is not None
        else None
    )
    if mismatch is not None:
        run.result = _failed(f"Agent contradicted its specification: {mismatch}")
        run.prob = problems.agent_error(spec.agent_id, mismatch)


def collect_delegations(conductor: Conductor, run: RunState) -> None:
    """Recorded whatever the agent did afterwards: the children ran and are stored."""
    if run.grant is not None:
        run.delegations = conductor._revoke_grant(run.grant)


def build_envelope(conductor: Conductor, run: RunState) -> None:
    """The envelope, with everything an agent must not decide about itself."""
    spec, request, profile = run.spec, run.request, conductor.profile
    assert run.result is not None, "a refusal or the agent decided the run"
    result, accepted = run.result, run.accepted
    run.envelope = Envelope(
        invocation_id=request.invocation_id,
        agent_id=spec.agent_id,
        agent_version=spec.version,
        completed_at=datetime.now(UTC),
        grounding_mode=spec.grounding_mode,
        policy_bundle_ref=profile.ref,
        policy_digest=profile.digest,
        acting_for=run.acting_for,
        contract_version=CONTRACT_VERSION,
        input_schema=accepted.digest if accepted else None,
        outcome=result.outcome,
        payload=result.payload,
        payload_schema=(
            spec.payload.digest if result.payload is not None and spec.payload else None
        ),
        evidence=result.evidence,
        telemetry=Telemetry(
            trace_id=run.trace_id,
            model_id=result.model_id,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            model_calls=list(run.model_calls),
        ),
        problem=run.prob,
        conversation_id=request.conversation_id,
        project_id=request.project_id,
        parent_invocation_id=request.parent_invocation_id,
        delegations=run.delegations,
    )


# Within the run's `invoke_agent` span, in order.
INSIDE_SPAN: tuple[Step, ...] = (
    gate,
    check_input,
    refuse,
    invoke_agent,
    collect_delegations,
    build_envelope,
)


# 6. Grounding linter, over the finished tree of this trace.
def lint_grounding(conductor: Conductor, run: RunState) -> None:
    run.watch.started(steps.GROUNDING)
    records = conductor.tracing.finished_records(run.trace_id)
    report = run.report = grounding.lint(records, run.finished.to_document())
    run.watch.grounding(report)
    run.watch.finished(steps.GROUNDING)
    conductor._keep_report(run.request.invocation_id, report)


# 6a. Source check, over the evidence the linter has just read (docs/specs/grounding.md).
def check_sources(conductor: Conductor, run: RunState) -> None:
    run.watch.started(steps.SOURCES)
    run.source_report = source_check.check(run.finished.to_document(), conductor.sources)
    run.watch.sources(run.source_report)
    run.watch.finished(steps.SOURCES)


def withhold_violations(conductor: Conductor, run: RunState) -> None:
    """A violation of the grounding linter or the source check withholds a succeeded result."""
    assert run.report is not None and run.source_report is not None
    withheld = [
        (check, found)
        for check, found in (
            ("the grounding linter", run.report.violations),
            ("the source check", run.source_report.violations),
        )
        if found
    ]
    if not withheld or run.finished.outcome.status != OutcomeStatus.SUCCEEDED:
        return
    violations = [v for _, found in withheld for v in found]
    statement = (
        "Output withheld: it failed "
        + " and ".join(check for check, _ in withheld)
        + ". "
        + "; ".join(violations)
    )
    run.envelope = failed(run.finished, statement, problems.grounding_violation(violations))


# 7. Validate. A result the agent returned that still breaks the contract is the agent's error,
# as a payload of the wrong class is: it is stored as failed(agent-error), not raised past the
# store. An envelope the conductor built itself that breaks the contract is a conductor bug, and
# raises.
def validate_contract(conductor: Conductor, run: RunState) -> None:
    run.doc = run.finished.to_document()
    try:
        validate.validate_envelope(run.doc)
    except validate.ContractViolation as exc:
        if not run.from_agent:
            raise
        statement = "Agent result violates the contract: " + "; ".join(exc.messages)
        prob = problems.agent_error(run.spec.agent_id, exc)
        run.envelope = failed(run.finished, statement, prob)
        run.doc = run.envelope.to_document()
        validate.validate_envelope(run.doc)


# 7a. The run's effects on its project (`dd_harness.project_effects`). A draft the project
# refuses fails the run, and that failed run is the record.
def apply_project_effects(conductor: Conductor, run: RunState) -> None:
    if conductor.projects is None:
        return
    refusal = conductor.projects.after_run(run.finished, acted_for=run.acting_for)
    if refusal is None:
        return
    statement = f"The draft was not kept in the project: {refusal}."
    run.envelope = failed(run.finished, statement, problems.revision_refused(refusal))
    run.doc = run.envelope.to_document()
    validate.validate_envelope(run.doc)


# 7b. The payload against its class's SHACL shapes. Reported, never withheld.
def check_shapes(conductor: Conductor, run: RunState) -> None:
    envelope, payload = run.finished, run.spec.payload
    if envelope.payload is None or payload is None or payload.shapes is None:
        return
    run.shapes_report = shacl.validate_payload(
        envelope.invocation_id, run.doc["payload"], payload, envelope.completed_at
    ).report_bytes()


# 8. Store, trace file, provenance. Everything else a run keeps is a named artifact beside it
# (docs/specs/storage.md).
def store_run(conductor: Conductor, run: RunState) -> None:
    store, envelope, accepted = conductor.store, run.finished, run.accepted
    assert run.report is not None and run.source_report is not None
    # The schemas the run was checked against, kept by digest for the viewer
    # (docs/specs/contract.md).
    checked = [accepted] if accepted else []
    if envelope.payload is not None and run.spec.payload is not None:
        checked.append(run.spec.payload)
    store.append(run.doc, run.request_doc, checked, run.prompts)
    run_id = envelope.invocation_id
    spans = conductor._spans(run.trace_id)
    store.put_artifact(run_id, SPANS, spans)
    store.put_artifact(run_id, GROUNDING, (run.report.summary() + "\n").encode())
    store.put_artifact(run_id, SOURCES, (run.source_report.summary() + "\n").encode())
    if run.shapes_report is not None:
        store.put_artifact(run_id, VALIDATION, run.shapes_report)
    if conductor.write_crate:
        crate = process_run_crate(run.doc, run.request_doc, spans, run.started, run.shapes_report)
        for name, data in crate.items():
            store.put_artifact(run_id, f"{CRATE}/{name}", data)


# Once the run's span has ended, in order.
AFTER_SPAN: tuple[Step, ...] = (
    lint_grounding,
    check_sources,
    withhold_violations,
    validate_contract,
    apply_project_effects,
    check_shapes,
    store_run,
)


def failed(envelope: Envelope, statement: str, prob: ProblemDetails) -> Envelope:
    """The envelope failed after the agent answered: what it returned is not kept."""
    return envelope.model_copy(
        update={
            "outcome": Outcome(status=OutcomeStatus.FAILED, statement=statement),
            "payload": None,
            "payload_schema": None,
            "evidence": [],
            "problem": prob,
        }
    )


def _input_refusal(spec: AgentSpec, document: dict[str, Any]) -> tuple[str, list[str]] | None:
    """Why the agent will not read this input: the class it names, and how the input fails that
    class's schema (no errors: the agent does not accept the class at all). None if it will."""
    got = str(document.get("schema_class"))
    accepted = spec.accepted(got)
    if accepted is None:
        return got, []
    errors = accepted.errors(document)
    return (got, errors) if errors else None


def _matched_prompts(result: AgentResult) -> tuple[dict[str, dict[str, Any]], str | None]:
    """The prompts the result's model calls name, each checked against its digest, and what is
    wrong if the prompts are not exactly those (docs/specs/disclosure.md). Only prompts that hash
    to their key are kept."""
    kept = {
        digest: dict(prompt)
        for digest, prompt in result.prompts.items()
        if prompt_digest(prompt) == digest
    }
    named = {call.prompt_digest for call in result.model_calls}
    problems_found = []
    if wrong := sorted(set(result.prompts) - set(kept)):
        problems_found.append(f"prompts that do not hash to their digest: {', '.join(wrong)}")
    if missing := sorted(named - set(kept)):
        problems_found.append(f"model calls whose prompt was not returned: {', '.join(missing)}")
    if extra := sorted(set(kept) - named):
        problems_found.append(f"prompts no model call names: {', '.join(extra)}")
        kept = {d: p for d, p in kept.items() if d in named}
    return kept, "; ".join(problems_found) or None


def _payload_mismatch(spec: AgentSpec, document: dict[str, Any]) -> TypeError | None:
    """How a returned payload contradicts the agent's declared payload class, or None."""
    got = document.get("schema_class")
    if spec.payload is None or got != spec.payload.name:
        declared = spec.payload.name if spec.payload else "none"
        return TypeError(f"returned {got}, declared {declared}")
    errors = spec.payload.errors(document)
    if errors:
        return TypeError(f"returned a {got} its class schema does not admit: {'; '.join(errors)}")
    return None

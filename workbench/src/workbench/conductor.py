"""The conductor: policy gate → input check → agent → grounding linter → source check →
validation → store → provenance.

`invoke` is a plain function. Every transport (CLI, A2A, AG-UI) is a wrapper around it
(ADR-0001). It fills in everything an agent must not decide about itself: identifiers,
timestamps, telemetry, the grounding mode and input hash it is held to, the human it acted for,
and whether the output passed the grounding check and the source check. It knows nothing about
any payload class.

The grounding linter checks the agent's account of its run for consistency; the source check
re-hashes what the evidence cites against a copy of the source the workbench holds (ADR-0016).
A violation of either withholds a succeeded result. Their verdicts are stored separately, in
`grounding.txt` and `sources.txt`.

Delegation (ADR-0012). When the conductor runs a remote agent in grounding mode `delegation`,
and it knows its own A2A address (`workbench_url`), it issues that invocation a grant: a random
token, sent with the request (never in `RunContext`), that the agent may present while the
invocation runs to ask the workbench to invoke another agent. `invoke_delegated` runs such a
request as an ordinary invocation, sets its lineage from the grant, and records the child
against the parent. The parent's envelope lists those records in `delegations`, which is what
the linter checks a relayed reply against. Delegation is one level deep: a child is never issued
a grant.

The human (ADR-0018). Every invocation acts for a principal, which the transport takes from its
authentication boundary and passes to `invoke`; the conductor keeps none of its own, so an
invocation without one cannot be written. A delegated child acts for its parent's principal,
carried on the grant: the caller on that path is an agent, not the human. The principal is
recorded in the envelope and the crate and is never sent to the agent.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from opentelemetry.trace import SpanContext
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from dd_sdk.agent import AgentResult, AgentSpec, RunContext, typed_request
from dd_sdk.contract import problem as problems
from dd_sdk.contract import validate
from dd_sdk.contract.models import (
    Delegation,
    Envelope,
    GroundingMode,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    Principal,
    ReasonCode,
    Telemetry,
    input_source_id,
    to_document,
)
from dd_sdk.contract.version import CONTRACT_VERSION
from dd_sdk.delegate import DelegationGrant
from dd_sdk.evidence import envelope_hash
from dd_sdk.evidence import input_hash as compute_input_hash
from dd_sdk.tracing import (
    ATTR_OUTCOME,
    Tracing,
    invoke_agent_span,
    make_tracing,
    policy_gate_span,
)
from workbench import grounding, policy
from workbench import sources as source_check
from workbench.provenance import write_process_run_crate
from workbench.registry import Registry
from workbench.remote import Received, RemoteAgent
from workbench.store import RunStore

DATA_STEWARD = "data_steward"


class UnknownAgent(Exception):
    pass


class DelegationError(ValueError):
    """A request's lineage is not one the conductor issued: a caller error, never an outcome."""


class DuplicateInvocation(ValueError):
    """A request reuses an `invocation_id` the conductor has run or is running: a caller error.

    Running it would overwrite the stored run, or collide with a parent still in flight.
    """


# The most recent grounding reports kept in memory, for a caller that reads one straight after
# `invoke` (the CLI, the evaluation). `grounding.txt` in each run directory is the durable copy.
GROUNDING_REPORTS_KEPT = 256


@dataclass
class Grant:
    """One delegation grant, live while its parent invocation runs."""

    token: str
    parent_invocation_id: str
    parent_agent_id: str
    conversation_id: str | None
    acting_for: Principal
    delegations: list[Delegation] = field(default_factory=list)
    # Children admitted under this grant and not yet finished; revocation waits for them.
    in_flight: int = 0


@dataclass
class Conductor:
    registry: Registry
    store: RunStore
    # The deployment's institutional profile, loaded once by whoever builds the conductor. Every
    # invocation, delegated or not, is gated by it; a request cannot name another (ADR-0017).
    profile: policy.Profile
    tracing: Tracing = field(default_factory=make_tracing)
    write_crate: bool = True
    grounding_reports: dict[str, grounding.GroundingReport] = field(default_factory=dict)
    # The copies of sources the source check resolves evidence against (ADR-0016). None held
    # means every externally sourced evidence item is reported as unresolved.
    sources: source_check.Sources = field(default_factory=source_check.Sources.none)
    # The workbench's own A2A address, sent to delegation agents as their callback. None (the
    # CLI) means no grant is issued and a delegation agent runs without `delegate`.
    workbench_url: str | None = None
    _grants: dict[str, Grant] = field(default_factory=dict, repr=False)
    _grants_lock: threading.Condition = field(default_factory=threading.Condition, repr=False)
    _running: set[str] = field(default_factory=set, repr=False)
    _running_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def invoke(self, request: InvocationRequest, *, acting_for: Principal) -> Envelope:
        """Run one top-level invocation on behalf of `acting_for`, the principal the caller's
        transport authenticated. Lineage is the conductor's to set, never the caller's."""
        if request.parent_invocation_id is not None:
            raise DelegationError(
                "parent_invocation_id is set by the conductor from a delegation grant; "
                "a caller may not set it"
            )
        return self._invoke(request, acting_for)

    def invoke_delegated(
        self, request: InvocationRequest, token: str, traceparent: str = ""
    ) -> Envelope:
        """Run a request a delegation agent sent back under its grant, and record it.

        Raises `DelegationError` for an unknown or expired token or an agent delegating to
        itself. The child's conversation and principal are the parent's, whatever the request or
        its caller says; its policy is the conductor's, as every invocation's is.
        """
        with self._grants_lock:
            grant = self._grants.get(token)
            if grant is None:
                raise DelegationError("unknown or expired delegation token")
            if request.agent_id == grant.parent_agent_id:
                raise DelegationError(f"{request.agent_id} may not delegate to itself")
            grant.in_flight += 1
        try:
            return self._invoke_child(grant, request, traceparent)
        finally:
            with self._grants_lock:
                grant.in_flight -= 1
                self._grants_lock.notify_all()

    def _invoke_child(self, grant: Grant, request: InvocationRequest, traceparent: str) -> Envelope:
        child = request.model_copy(
            update={
                "parent_invocation_id": grant.parent_invocation_id,
                "conversation_id": grant.conversation_id,
            }
        )
        envelope = self._invoke(child, grant.acting_for, link=_span_context(traceparent))
        record = Delegation(
            delegated_invocation_id=envelope.invocation_id,
            delegated_agent_id=envelope.agent_id,
            delegated_agent_version=envelope.agent_version,
            delegated_status=envelope.outcome.status,
            content_hash=envelope_hash(envelope.to_document()),
        )
        with self._grants_lock:
            grant.delegations.append(record)
        return envelope

    def _issue_grant(self, request: InvocationRequest, acting_for: Principal) -> Grant:
        grant = Grant(
            token=secrets.token_urlsafe(32),
            parent_invocation_id=request.invocation_id,
            parent_agent_id=request.agent_id,
            conversation_id=request.conversation_id,
            acting_for=acting_for,
        )
        with self._grants_lock:
            self._grants[grant.token] = grant
        return grant

    def _revoke_grant(self, grant: Grant) -> list[Delegation]:
        """Refuse further children, wait for those already admitted, and return the records.

        A child still running when its parent finishes (the parent's delegate call timed out, or
        the parent did not wait) is stored with the parent's id, so the parent must list it. The
        wait needs no timeout of its own: each child is bounded by its agent's transport timeout.
        """
        with self._grants_lock:
            self._grants.pop(grant.token, None)
            self._grants_lock.wait_for(lambda: grant.in_flight == 0)
            return list(grant.delegations)

    def _invoke(
        self, request: InvocationRequest, acting_for: Principal, link: SpanContext | None = None
    ) -> Envelope:
        request_doc = to_document(request)
        validate.validate_request(request_doc)  # raises: a malformed request is a caller bug
        invocation_id = request.invocation_id
        with self._running_lock:
            if invocation_id in self._running or self.store.has(invocation_id):
                raise DuplicateInvocation(
                    f"invocation_id {invocation_id} has already been used; "
                    "send each request with a new one"
                )
            self._running.add(invocation_id)
        try:
            return self._run(request, request_doc, acting_for, link)
        finally:
            with self._running_lock:
                self._running.discard(invocation_id)

    def _run(
        self,
        request: InvocationRequest,
        request_doc: dict[str, Any],
        acting_for: Principal,
        link: SpanContext | None,
    ) -> Envelope:
        agent = self.registry.get(request.agent_id)
        if agent is None:
            raise UnknownAgent(
                f"no agent registered as {request.agent_id!r}; known: {self.registry.ids()}"
                + self.registry.not_registered()
            )
        spec = agent.spec
        started = datetime.now(UTC)
        tracer = self.tracing.tracer
        input_hash = compute_input_hash(request_doc["input"])
        # The class schema the card carries for the input, if the agent accepts its class.
        accepted = spec.accepted(str(request_doc["input"].get("schema_class")))
        input_ref = input_source_id(request.invocation_id)

        delegations: list[Delegation] = []
        grant: Grant | None = None
        from_agent = False
        with invoke_agent_span(
            tracer, spec.agent_id, spec.grounding_mode.value, input_hash, link=link
        ) as root:
            trace_id = format(root.get_span_context().trace_id, "032x")

            # 1. Policy gate, against the deployment's profile.
            profile = self.profile
            with policy_gate_span(tracer, spec.agent_id):
                decision = policy.gate(profile, spec.agent_id, spec.action_class)
            result: AgentResult
            if not decision.allowed:
                result = AgentResult(
                    outcome=Outcome(
                        status=OutcomeStatus.FAILED,
                        statement=f"{decision.reason}. The agent was not run.",
                    ),
                )
                prob = (
                    problems.action_class_mismatch(
                        spec.agent_id,
                        spec.action_class,
                        profile.agents[spec.agent_id],
                        profile.profile_id,
                    )
                    if decision.refusal == "action-class-mismatch"
                    else problems.agent_not_permitted(spec.agent_id, profile.profile_id)
                )
            elif decision.requires_approval:
                result = AgentResult(
                    outcome=Outcome(
                        status=OutcomeStatus.REFERRED,
                        reason_code=ReasonCode.POLICY_REQUIRES_APPROVAL,
                        referred_to=DATA_STEWARD,
                        statement=f"{decision.reason}. The agent was not run.",
                    )
                )
                prob = None
            elif refused := _input_refusal(spec, request_doc["input"]):
                # 2. Input check, against the class schema the agent's card carries (ADR-0019).
                # A valid request addressed to an agent that does not read this input is an
                # outcome, not an exception: the caller, the store and a reviewer all see the
                # refusal as an envelope, as they do a policy refusal.
                got, errors = refused
                statement = (
                    f"The input is not a valid {got}: {'; '.join(errors)}."
                    if errors
                    else f"{spec.agent_id} accepts {', '.join(spec.accepts_names())}, not {got}."
                )
                result = AgentResult(
                    outcome=Outcome(
                        status=OutcomeStatus.FAILED,
                        statement=f"{statement} The agent was not run.",
                    )
                )
                prob = problems.input_not_accepted(
                    spec.agent_id, got, spec.accepts_names(), tuple(errors)
                )
            else:
                # 3. Run the agent. An exception becomes a failed outcome; never a crash.
                prob = None
                # A grant travels on the A2A wire, so only a remote agent can be sent one.
                sent_grant: DelegationGrant | None = None
                if (
                    spec.grounding_mode == GroundingMode.DELEGATION
                    and request.parent_invocation_id is None
                    and self.workbench_url is not None
                    and isinstance(agent, RemoteAgent)
                ):
                    grant = self._issue_grant(request, acting_for)
                    sent_grant = DelegationGrant(url=self.workbench_url, token=grant.token)
                ctx = RunContext(tracer=tracer, input_ref=input_ref, input_hash=input_hash)
                try:
                    # An in-process agent records its spans in this trace already.
                    received = (
                        agent.call(request, ctx, sent_grant)
                        if isinstance(agent, RemoteAgent)
                        else Received(agent.run(typed_request(spec, request), ctx))
                    )
                except Exception as exc:  # noqa: BLE001 — converted to a failed outcome by design
                    result = AgentResult(
                        outcome=Outcome(
                            status=OutcomeStatus.FAILED, statement=f"Agent raised: {exc}"
                        )
                    )
                    prob = problems.agent_error(spec.agent_id, exc)
                else:
                    from_agent = True
                    # A remote agent's spans were recorded in its own process; bring them into
                    # this trace so the linter reads one tree (ADR-0011).
                    self.tracing.import_spans(trace_id, received.spans)
                    result = received.result
                    # An agent that returns a payload other than the class it declared, or one
                    # its own class schema does not admit, is contradicting its specification: a
                    # programmer error, handled the same way as an exception.
                    if result.payload is not None and (
                        mismatch := _payload_mismatch(spec, to_document(result.payload))
                    ):
                        result = AgentResult(
                            outcome=Outcome(
                                status=OutcomeStatus.FAILED,
                                statement=f"Agent contradicted its specification: {mismatch}",
                            )
                        )
                        prob = problems.agent_error(spec.agent_id, mismatch)

            if grant is not None:
                # Recorded whatever the agent did afterwards: the children ran and are stored.
                delegations = self._revoke_grant(grant)

            envelope = Envelope(
                invocation_id=request.invocation_id,
                agent_id=spec.agent_id,
                agent_version=spec.version,
                completed_at=datetime.now(UTC),
                grounding_mode=spec.grounding_mode,
                policy_bundle_ref=profile.ref,
                policy_digest=profile.digest,
                acting_for=acting_for,
                contract_version=CONTRACT_VERSION,
                input_schema=accepted.digest if accepted else None,
                outcome=result.outcome,
                payload=result.payload,
                payload_schema=(
                    spec.payload.digest if result.payload is not None and spec.payload else None
                ),
                evidence=result.evidence,
                telemetry=Telemetry(
                    trace_id=trace_id,
                    model_id=result.model_id,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                ),
                problem=prob,
                conversation_id=request.conversation_id,
                parent_invocation_id=request.parent_invocation_id,
                delegations=delegations,
            )
            root.set_attribute(ATTR_OUTCOME, envelope.outcome.status.value)

        try:
            # 4. Grounding linter, over the finished tree of this trace.
            records = self.tracing.finished_records(trace_id)
            report = grounding.lint(records, envelope.to_document())
            self.grounding_reports[request.invocation_id] = report
            while len(self.grounding_reports) > GROUNDING_REPORTS_KEPT:
                del self.grounding_reports[next(iter(self.grounding_reports))]
            # 4a. Source check, over the evidence the linter has just read (ADR-0016).
            source_report = source_check.check(envelope.to_document(), self.sources)
            withheld = [
                (check, found)
                for check, found in (
                    ("the grounding linter", report.violations),
                    ("the source check", source_report.violations),
                )
                if found
            ]
            if withheld and envelope.outcome.status == OutcomeStatus.SUCCEEDED:
                violations = [v for _, found in withheld for v in found]
                envelope = envelope.model_copy(
                    update={
                        "outcome": Outcome(
                            status=OutcomeStatus.FAILED,
                            statement="Output withheld: it failed "
                            + " and ".join(check for check, _ in withheld)
                            + ". "
                            + "; ".join(violations),
                        ),
                        "payload": None,
                        "payload_schema": None,
                        "evidence": [],
                        "problem": problems.grounding_violation(violations),
                    }
                )

            # 5. Validate, store, trace file, provenance. A result the agent returned that still
            # breaks the contract is the agent's error, as a payload of the wrong class is: it is
            # stored as failed(agent-error), not raised past the store. An envelope the conductor
            # built itself that breaks the contract is a conductor bug, and raises.
            doc = envelope.to_document()
            if from_agent:
                try:
                    validate.validate_envelope(doc)
                except validate.ContractViolation as exc:
                    envelope = envelope.model_copy(
                        update={
                            "outcome": Outcome(
                                status=OutcomeStatus.FAILED,
                                statement="Agent result violates the contract: "
                                + "; ".join(exc.messages),
                            ),
                            "payload": None,
                            "payload_schema": None,
                            "evidence": [],
                            "problem": problems.agent_error(spec.agent_id, exc),
                        }
                    )
                    doc = envelope.to_document()
            validate.validate_envelope(doc)
            # The schemas the run was checked against, kept by digest for the viewer (ADR-0019).
            checked = [accepted] if accepted else []
            if envelope.payload is not None and spec.payload is not None:
                checked.append(spec.payload)
            run_dir = self.store.append(doc, request_doc, checked)
            spans_path = run_dir / "spans.jsonl"
            self.tracing.write_jsonl(spans_path, trace_id)
            (run_dir / "grounding.txt").write_text(report.summary() + "\n", encoding="utf-8")
            (run_dir / "sources.txt").write_text(source_report.summary() + "\n", encoding="utf-8")
            if self.write_crate:
                write_process_run_crate(
                    run_dir,
                    doc,
                    run_dir / "request.json",
                    run_dir / "envelope.json",
                    spans_path,
                    started,
                )
        finally:
            # spans.jsonl is the durable copy; a long-running server must not keep them all.
            self.tracing.discard(trace_id)
        return envelope


def _input_refusal(spec: AgentSpec, document: dict[str, Any]) -> tuple[str, list[str]] | None:
    """Why the agent will not read this input: the class it names, and how the input fails that
    class's schema (no errors: the agent does not accept the class at all). None if it will."""
    got = str(document.get("schema_class"))
    accepted = spec.accepted(got)
    if accepted is None:
        return got, []
    errors = accepted.errors(document)
    return (got, errors) if errors else None


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


def _span_context(traceparent: str) -> SpanContext | None:
    """The span a W3C `traceparent` names, or None if it names none."""
    from opentelemetry import trace

    ctx = TraceContextTextMapPropagator().extract({"traceparent": traceparent})
    span_context = trace.get_current_span(ctx).get_span_context()
    return span_context if span_context.is_valid else None

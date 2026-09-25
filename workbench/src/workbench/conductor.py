"""The conductor: policy gate → input check → agent → grounding linter → validation → store →
provenance.

`invoke` is a plain function. Every transport (CLI, A2A, AG-UI) is a wrapper around it
(ADR-0001). It fills in everything an agent must not decide about itself: identifiers,
timestamps, telemetry, the grounding mode and input hash it is held to, and whether the output
passed the grounding check. It knows nothing about any payload class.

Delegation (ADR-0012). When the conductor runs an agent in grounding mode `delegation`, and it
knows its own A2A address (`workbench_url`), it issues that invocation a grant: a random token
the agent may present, while the invocation runs, to ask the workbench to invoke another agent.
`invoke_delegated` runs such a request as an ordinary invocation, sets its lineage from the
grant, and records the child against the parent. The parent's envelope lists those records in
`delegations`, which is what the linter checks a relayed reply against. Delegation is one level
deep: a child is never issued a grant.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from opentelemetry.trace import SpanContext
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from dd_sdk.agent import AgentResult, DelegationGrant, RunContext
from dd_sdk.contract import problem as problems
from dd_sdk.contract import validate
from dd_sdk.contract.models import (
    Delegation,
    Envelope,
    GroundingMode,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    Telemetry,
    input_source_id,
    to_document,
)
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
from workbench.provenance import write_process_run_crate
from workbench.registry import Registry
from workbench.store import RunStore

DATA_STEWARD = "data_steward"


class UnknownAgent(Exception):
    pass


class DelegationError(ValueError):
    """A request's lineage is not one the conductor issued: a caller error, never an outcome."""


@dataclass
class Grant:
    """One delegation grant, live while its parent invocation runs."""

    token: str
    parent_invocation_id: str
    parent_agent_id: str
    conversation_id: str | None
    policy_bundle_ref: str
    delegations: list[Delegation] = field(default_factory=list)


@dataclass
class Conductor:
    registry: Registry
    store: RunStore
    profiles_dir: Path = policy.PROFILES_DIR
    tracing: Tracing = field(default_factory=make_tracing)
    write_crate: bool = True
    grounding_reports: dict[str, grounding.GroundingReport] = field(default_factory=dict)
    # The workbench's own A2A address, sent to delegation agents as their callback. None (the
    # CLI) means no grant is issued and a delegation agent runs without `delegate`.
    workbench_url: str | None = None
    _grants: dict[str, Grant] = field(default_factory=dict, repr=False)
    _grants_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def invoke(self, request: InvocationRequest) -> Envelope:
        """Run one top-level invocation. Lineage is the conductor's to set, never the caller's."""
        if request.parent_invocation_id is not None:
            raise DelegationError(
                "parent_invocation_id is set by the conductor from a delegation grant; "
                "a caller may not set it"
            )
        return self._invoke(request)

    def invoke_delegated(
        self, request: InvocationRequest, token: str, traceparent: str = ""
    ) -> Envelope:
        """Run a request a delegation agent sent back under its grant, and record it.

        Raises `DelegationError` for an unknown or expired token or an agent delegating to
        itself. The child's conversation and policy are the parent's, whatever the request says.
        """
        with self._grants_lock:
            grant = self._grants.get(token)
        if grant is None:
            raise DelegationError("unknown or expired delegation token")
        if request.agent_id == grant.parent_agent_id:
            raise DelegationError(f"{request.agent_id} may not delegate to itself")
        child = request.model_copy(
            update={
                "parent_invocation_id": grant.parent_invocation_id,
                "conversation_id": grant.conversation_id,
                "policy_bundle_ref": grant.policy_bundle_ref,
            }
        )
        envelope = self._invoke(child, link=_span_context(traceparent))
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

    def _issue_grant(self, request: InvocationRequest) -> Grant:
        grant = Grant(
            token=secrets.token_urlsafe(32),
            parent_invocation_id=request.invocation_id,
            parent_agent_id=request.agent_id,
            conversation_id=request.conversation_id,
            policy_bundle_ref=request.policy_bundle_ref,
        )
        with self._grants_lock:
            self._grants[grant.token] = grant
        return grant

    def _revoke_grant(self, grant: Grant) -> list[Delegation]:
        with self._grants_lock:
            self._grants.pop(grant.token, None)
            return list(grant.delegations)

    def _invoke(self, request: InvocationRequest, link: SpanContext | None = None) -> Envelope:
        request_doc = to_document(request)
        validate.validate_request(request_doc)  # raises: a malformed request is a caller bug
        agent = self.registry.get(request.agent_id)
        if agent is None:
            unavailable = "".join(
                f"\n  {name} unavailable: {reason}"
                for name, reason in self.registry.unavailable.items()
            )
            raise UnknownAgent(
                f"no agent registered as {request.agent_id!r}; known: {self.registry.ids()}"
                + unavailable
            )
        spec = agent.spec
        started = datetime.now(UTC)
        tracer = self.tracing.tracer
        input_hash = compute_input_hash(request_doc["input"])
        input_ref = input_source_id(request.invocation_id)

        delegations: list[Delegation] = []
        grant: Grant | None = None
        from_agent = False
        with invoke_agent_span(
            tracer, spec.agent_id, spec.grounding_mode.value, input_hash, link=link
        ) as root:
            trace_id = format(root.get_span_context().trace_id, "032x")

            # 1. Policy gate.
            profile = policy.load_profile(request.policy_bundle_ref, self.profiles_dir)
            with policy_gate_span(tracer, spec.agent_id):
                decision = policy.gate(profile, spec.agent_id, spec.action_class)
            result: AgentResult
            if not decision.allowed:
                result = AgentResult(
                    outcome=Outcome(status=OutcomeStatus.FAILED, statement=decision.reason),
                )
                prob = problems.agent_not_permitted(spec.agent_id, profile.profile_id)
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
            elif not isinstance(request.input, spec.accepts):
                # 2. Input check. A valid request addressed to an agent that does not read this
                # input class is an outcome, not an exception: the caller, the store and a
                # reviewer all see the refusal as an envelope, as they do a policy refusal.
                got = type(request.input).__name__
                result = AgentResult(
                    outcome=Outcome(
                        status=OutcomeStatus.FAILED,
                        statement=(
                            f"{spec.agent_id} accepts {', '.join(spec.accepts_names())}, "
                            f"not {got}. The agent was not run."
                        ),
                    )
                )
                prob = problems.input_not_accepted(spec.agent_id, got, spec.accepts_names())
            else:
                # 3. Run the agent. An exception becomes a failed outcome; never a crash.
                prob = None
                if (
                    spec.grounding_mode == GroundingMode.DELEGATION
                    and request.parent_invocation_id is None
                    and self.workbench_url is not None
                ):
                    grant = self._issue_grant(request)
                try:
                    result = agent.run(
                        request,
                        RunContext(
                            tracer=tracer,
                            input_ref=input_ref,
                            input_hash=input_hash,
                            grant=(
                                DelegationGrant(url=self.workbench_url or "", token=grant.token)
                                if grant is not None
                                else None
                            ),
                        ),
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
                    self.tracing.import_spans(trace_id, result.spans)
                    # An agent that returns a payload other than the class it declared is
                    # contradicting its own specification: a programmer error, handled the same
                    # way as an exception.
                    if result.payload is not None and (
                        spec.payload_type is None
                        or not isinstance(result.payload, spec.payload_type)
                    ):
                        declared = spec.payload_type.__name__ if spec.payload_type else "none"
                        mismatch = TypeError(
                            f"returned {type(result.payload).__name__}, declared {declared}"
                        )
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
                outcome=result.outcome,
                payload=result.payload,
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

        # 4. Grounding linter, over the finished tree of this trace.
        records = self.tracing.finished_records(trace_id)
        report = grounding.lint(records, envelope.to_document())
        self.grounding_reports[request.invocation_id] = report
        if not report.passed and envelope.outcome.status == OutcomeStatus.SUCCEEDED:
            envelope = envelope.model_copy(
                update={
                    "outcome": Outcome(
                        status=OutcomeStatus.FAILED,
                        statement="Output withheld: it failed the grounding linter. "
                        + "; ".join(report.violations),
                    ),
                    "payload": None,
                    "evidence": [],
                    "problem": problems.grounding_violation(report.violations),
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
                        "evidence": [],
                        "problem": problems.agent_error(spec.agent_id, exc),
                    }
                )
                doc = envelope.to_document()
        validate.validate_envelope(doc)
        run_dir = self.store.append(doc, request_doc)
        spans_path = run_dir / "spans.jsonl"
        self.tracing.write_jsonl(spans_path, trace_id)
        (run_dir / "grounding.txt").write_text(report.summary() + "\n", encoding="utf-8")
        if self.write_crate:
            write_process_run_crate(
                run_dir,
                doc,
                run_dir / "request.json",
                run_dir / "envelope.json",
                spans_path,
                started,
            )
        return envelope


def _span_context(traceparent: str) -> SpanContext | None:
    """The span a W3C `traceparent` names, or None if it names none."""
    from opentelemetry import trace

    ctx = TraceContextTextMapPropagator().extract({"traceparent": traceparent})
    span_context = trace.get_current_span(ctx).get_span_context()
    return span_context if span_context.is_valid else None

"""The conductor: policy gate → input check → agent → grounding linter → validation → store →
provenance.

`invoke` is a plain function. Every transport (CLI, A2A, AG-UI) is a wrapper around it
(ADR-0001). It fills in everything an agent must not decide about itself: identifiers,
timestamps, telemetry, the grounding mode and input hash it is held to, and whether the output
passed the grounding check. It knows nothing about any payload class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from workbench import grounding, policy
from workbench.agents.base import AgentResult, RunContext
from workbench.agents.registry import Registry
from workbench.contract import problem as problems
from workbench.contract import validate
from workbench.contract.models import (
    Envelope,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    Telemetry,
    input_source_id,
    to_document,
)
from workbench.evidence import input_hash as compute_input_hash
from workbench.provenance import write_process_run_crate
from workbench.store import RunStore
from workbench.tracing import (
    ATTR_OUTCOME,
    Tracing,
    invoke_agent_span,
    make_tracing,
    policy_gate_span,
)

DATA_STEWARD = "data_steward"


class UnknownAgent(Exception):
    pass


@dataclass
class Conductor:
    registry: Registry
    store: RunStore
    profiles_dir: Path = policy.PROFILES_DIR
    tracing: Tracing = field(default_factory=make_tracing)
    write_crate: bool = True
    grounding_reports: dict[str, grounding.GroundingReport] = field(default_factory=dict)

    def invoke(self, request: InvocationRequest) -> Envelope:
        request_doc = to_document(request)
        validate.validate_request(request_doc)  # raises: a malformed request is a caller bug
        agent = self.registry.get(request.agent_id)
        if agent is None:
            raise UnknownAgent(
                f"no agent registered as {request.agent_id!r}; known: {self.registry.ids()}"
            )
        spec = agent.spec
        started = datetime.now(UTC)
        tracer = self.tracing.tracer
        input_hash = compute_input_hash(request_doc["input"])
        input_ref = input_source_id(request.invocation_id)

        with invoke_agent_span(
            tracer, spec.agent_id, spec.grounding_mode.value, input_hash
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
                try:
                    result = agent.run(
                        request,
                        RunContext(tracer=tracer, input_ref=input_ref, input_hash=input_hash),
                    )
                except Exception as exc:  # noqa: BLE001 — converted to a failed outcome by design
                    result = AgentResult(
                        outcome=Outcome(
                            status=OutcomeStatus.FAILED, statement=f"Agent raised: {exc}"
                        )
                    )
                    prob = problems.agent_error(spec.agent_id, exc)
                else:
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

        # 5. Validate, store, trace file, provenance.
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

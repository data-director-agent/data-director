"""The conductor: policy gate → agent → grounding linter → validation → store → provenance.

`invoke` is a plain function. Every transport (CLI, A2A, AG-UI) is a wrapper around it
(ADR-0001). It fills in everything an agent must not decide about itself: identifiers,
timestamps, telemetry, and whether the output passed the grounding check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from workbench import grounding, policy
from workbench.agents.base import Agent, AgentResult, RunContext
from workbench.contract import problem as problems
from workbench.contract import validate
from workbench.contract.models import (
    Envelope,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    Telemetry,
    to_document,
)
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
    agents: dict[str, Agent]
    store: RunStore
    profiles_dir: Path = policy.PROFILES_DIR
    tracing: Tracing = field(default_factory=make_tracing)
    write_crate: bool = True
    grounding_reports: dict[str, grounding.GroundingReport] = field(default_factory=dict)

    def invoke(self, request: InvocationRequest) -> Envelope:
        request_doc = to_document(request)
        validate.validate_request(request_doc)  # raises: a malformed request is a caller bug
        agent = self.agents.get(request.agent_id)
        if agent is None:
            raise UnknownAgent(
                f"no agent registered as {request.agent_id!r}; known: {sorted(self.agents)}"
            )
        started = datetime.now(UTC)
        tracer = self.tracing.tracer

        with invoke_agent_span(tracer, agent.agent_id) as root:
            trace_id = format(root.get_span_context().trace_id, "032x")

            # 1. Policy gate.
            profile = policy.load_profile(request.policy_bundle_ref, self.profiles_dir)
            with policy_gate_span(tracer, agent.agent_id):
                decision = policy.gate(profile, agent.agent_id, agent.action_class)
            result: AgentResult
            if not decision.allowed:
                result = AgentResult(
                    outcome=Outcome(status=OutcomeStatus.FAILED, statement=decision.reason),
                )
                prob = problems.agent_not_permitted(agent.agent_id, profile.profile_id)
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
            else:
                # 2. Run the agent. An exception becomes a failed outcome; never a crash.
                prob = None
                try:
                    result = agent.run(request, RunContext(tracer=tracer))
                except Exception as exc:  # noqa: BLE001 — converted to a failed outcome by design
                    result = AgentResult(
                        outcome=Outcome(
                            status=OutcomeStatus.FAILED, statement=f"Agent raised: {exc}"
                        )
                    )
                    prob = problems.agent_error(agent.agent_id, exc)

            envelope = Envelope(
                invocation_id=request.invocation_id,
                agent_id=agent.agent_id,
                agent_version=agent.version,
                completed_at=datetime.now(UTC),
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

        # 3. Grounding linter, over the finished tree of this trace.
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

        # 4. Validate, store, trace file, provenance.
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

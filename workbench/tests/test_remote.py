"""Agents behind A2A (ADR-0011): what crosses the wire, and what the conductor does with it.

Every harness test already reaches its agent through `workbench.testing.in_process`, so the wire
is exercised throughout. The tests here pin what is specific to an agent running elsewhere: its
spans join the conductor's trace, a span outside the invocation or carrying a conductor
attribute is a grounding violation, and a slow or unreachable agent is a failed envelope.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from opentelemetry import context as otel_context

from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import (
    GroundingMode,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)
from dd_sdk.tracing import ATTR_GROUNDING_MODE, ATTR_INPUT_HASH, records_from_jsonl
from workbench.conductor import Conductor
from workbench.registry import Registry
from workbench.remote import RemoteAgent
from workbench.store import RunStore
from workbench.testing import (
    SOURCE_A,
    ScriptedAgent,
    claim,
    fact_check_over,
    in_process,
    make_conductor,
    request,
    review_of_input,
)


def spans_of(runs_dir: Path, invocation_id: str) -> list[dict[str, object]]:
    path = runs_dir / invocation_id / "spans.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@pytest.mark.requirement("DD-REMOTE-AGENT", "DD-GROUNDING")
def test_agent_spans_join_the_conductors_trace_under_invoke_agent(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.RETRIEVAL, fact_check_over(SOURCE_A), steps=[SOURCE_A])
    req = request(agent.spec.agent_id, claim())
    env = make_conductor(runs_dir, agent).invoke(req)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement

    records = records_from_jsonl(spans_of(runs_dir, req.invocation_id))
    (root,) = [r for r in records if r.name == "invoke_agent"]
    (retrieval,) = [r for r in records if r.name == "retrieval"]
    assert retrieval.trace_id == root.trace_id == env.telemetry.trace_id
    assert retrieval.parent_id == root.span_id  # parented through the traceparent sent


def _spoofing(attribute: str, value: str) -> ScriptedAgent:
    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        with ctx.tracer.start_as_current_span("chat") as span:
            span.set_attribute(attribute, value)
        return review_of_input(req, ctx)

    return ScriptedAgent(GroundingMode.INPUT_ONLY, behaviour)


@pytest.mark.requirement("DD-REMOTE-AGENT", "DD-GROUNDING-MODE")
@pytest.mark.parametrize(
    ("attribute", "value"), [(ATTR_GROUNDING_MODE, "none"), (ATTR_INPUT_HASH, "0" * 64)]
)
def test_a_span_carrying_a_conductor_attribute_is_withheld(
    runs_dir: Path, attribute: str, value: str
) -> None:
    agent = _spoofing(attribute, value)
    env = make_conductor(runs_dir, agent).invoke(request(agent.spec.agent_id))
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith("/grounding-violation")
    assert attribute in env.outcome.statement


@pytest.mark.requirement("DD-REMOTE-AGENT", "DD-GROUNDING-MODE")
def test_a_span_outside_the_invocations_trace_is_withheld(runs_dir: Path) -> None:
    """A `none` agent that hides its model call in a trace of its own does not escape N1."""

    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        token = otel_context.attach(otel_context.Context())  # no parent: a new trace
        try:
            with ctx.tracer.start_as_current_span("chat"):
                pass
        finally:
            otel_context.detach(token)
        return review_of_input(req, ctx)

    agent = ScriptedAgent(GroundingMode.NONE, behaviour)
    env = make_conductor(runs_dir, agent).invoke(request(agent.spec.agent_id))
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith("/grounding-violation")
    assert "not the invocation's trace" in env.outcome.statement


@pytest.mark.requirement("DD-REMOTE-AGENT", "DD-OUTCOME")
def test_an_agent_that_exceeds_its_timeout_is_a_failed_envelope(runs_dir: Path) -> None:
    def slow(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        time.sleep(0.5)
        return review_of_input(req, ctx)

    remote = in_process(ScriptedAgent(GroundingMode.NONE, slow), timeout_s=0.1)
    conductor = Conductor(
        registry=Registry.from_agents([remote]), store=RunStore(runs_dir), write_crate=False
    )
    env = conductor.invoke(request(remote.spec.agent_id))
    assert env.outcome.status == OutcomeStatus.FAILED
    # Over HTTP the client's deadline raises TimeoutError; in process the A2A handler absorbs the
    # cancellation and returns the task still working. Either way the envelope is agent-error.
    assert env.problem is not None and env.problem.type.endswith("/agent-error")


@pytest.mark.requirement("DD-REMOTE-AGENT", "DD-OUTCOME")
def test_an_agent_that_goes_away_after_registration_is_a_failed_envelope(runs_dir: Path) -> None:
    registered = in_process(ScriptedAgent(GroundingMode.NONE, review_of_input))

    def refused(base_url: str, timeout_s: float) -> httpx.AsyncClient:
        raise httpx.ConnectError(f"connection refused: {base_url}")

    gone = RemoteAgent(spec=registered.spec, url=registered.url, client_factory=refused)
    conductor = Conductor(
        registry=Registry.from_agents([gone]), store=RunStore(runs_dir), write_crate=False
    )
    env = conductor.invoke(request(gone.spec.agent_id))
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and "connection refused" in (env.problem.detail or "")


def test_an_in_process_agent_and_its_remote_twin_produce_the_same_outcome(runs_dir: Path) -> None:
    """The wire adds nothing and loses nothing a harness test can see."""
    result = AgentResult(
        outcome=Outcome(
            status=OutcomeStatus.ABSTAINED,
            reason_code=ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
            statement="Nothing.",
        )
    )
    agent = ScriptedAgent(GroundingMode.NONE, result)
    direct = make_conductor(runs_dir / "direct", agent, remote=False).invoke(
        request(agent.spec.agent_id)
    )
    wired = make_conductor(runs_dir / "wired", agent).invoke(request(agent.spec.agent_id))
    assert direct.outcome == wired.outcome
    assert direct.grounding_mode == wired.grounding_mode
    assert agent.calls == 2

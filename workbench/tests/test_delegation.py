"""Delegation through the workbench (ADR-0012): a delegation agent's call back to the workbench,
over the in-memory A2A wire, runs a governed and stored child invocation that the parent records.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import (
    GroundingMode,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    new_invocation_id,
)
from dd_sdk.delegate import DelegationRefused
from dd_sdk.evidence import envelope_hash
from dd_sdk.tracing import records_from_jsonl
from workbench import grounding
from workbench.conductor import DelegationError, DuplicateInvocation
from workbench.testing import (
    ScriptedAgent,
    grant_token,
    make_conductor,
    message,
    record,
    reply_over,
    request,
    review_of_input,
)


def child_agent(**overrides: Any) -> ScriptedAgent:
    return ScriptedAgent(GroundingMode.NONE, review_of_input, **overrides)


def delegating(*targets: str) -> ScriptedAgent:
    """A delegation agent that delegates `record()` to each target and relays the results."""

    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert ctx.delegate is not None
        return reply_over(ctx, *(ctx.delegate(t, record()) for t in targets))

    return ScriptedAgent(GroundingMode.DELEGATION, behaviour)


def abstain(statement: str) -> AgentResult:
    return AgentResult(
        outcome=Outcome(
            status=OutcomeStatus.ABSTAINED,
            reason_code=ReasonCode.OUTSIDE_AGENT_SCOPE,
            statement=statement,
        )
    )


def lint_stored(runs: Path, invocation_id: str) -> grounding.GroundingReport:
    run_dir = runs / invocation_id
    spans = [json.loads(line) for line in (run_dir / "spans.jsonl").read_text().splitlines()]
    envelope = json.loads((run_dir / "envelope.json").read_text())
    return grounding.lint(records_from_jsonl(spans), envelope)


@pytest.mark.requirement("DD-DELEGATION")
@pytest.mark.requirement("C13.1")
def test_a_delegated_child_is_stored_with_its_lineage_and_recorded_by_the_parent(
    tmp_path: Path,
) -> None:
    conductor = make_conductor(tmp_path, delegating("fake.none"), child_agent())
    conversation = new_invocation_id()
    parent_request = request("fake.delegation", message()).model_copy(
        update={"conversation_id": conversation}
    )
    parent = conductor.invoke(parent_request)

    assert parent.outcome.status == OutcomeStatus.SUCCEEDED, parent.outcome.statement
    assert parent.conversation_id == conversation
    [delegation] = parent.delegations
    assert (delegation.delegated_agent_id, delegation.delegated_agent_version) == ("fake.none", "0")
    assert delegation.delegated_status == OutcomeStatus.SUCCEEDED

    child = conductor.store.get(delegation.delegated_invocation_id)
    assert child is not None
    assert child["parent_invocation_id"] == parent.invocation_id
    assert child["conversation_id"] == conversation
    stored = json.loads((tmp_path / child["invocation_id"] / "envelope.json").read_text())
    assert envelope_hash(stored) == delegation.content_hash  # DD-EVIDENCE: reproducible

    # Children are stored before their parent, each in a trace of its own, and both lint clean.
    order = [e["invocation_id"] for e in conductor.store.iter_envelopes()]
    assert order == [child["invocation_id"], parent.invocation_id]
    assert child["telemetry"]["trace_id"] != parent.telemetry.trace_id
    assert lint_stored(tmp_path, parent.invocation_id).passed
    assert lint_stored(tmp_path, child["invocation_id"]).passed


@pytest.mark.requirement("DD-DELEGATION")
def test_only_a_delegation_agent_is_given_a_grant(tmp_path: Path) -> None:
    seen: list[RunContext] = []

    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        seen.append(ctx)
        return review_of_input(req, ctx)

    conductor = make_conductor(tmp_path, ScriptedAgent(GroundingMode.NONE, behaviour))
    conductor.invoke(request("fake.none"))
    assert seen[0].delegate is None


@pytest.mark.requirement("DD-DELEGATION")
def test_a_caller_may_not_set_lineage_or_use_an_unknown_or_expired_token(tmp_path: Path) -> None:
    tokens: list[str] = []

    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        tokens.append(grant_token(ctx))
        return abstain("Kept the token.")

    conductor = make_conductor(tmp_path, ScriptedAgent(GroundingMode.DELEGATION, behaviour))
    forged = request("fake.delegation", message()).model_copy(
        update={"parent_invocation_id": new_invocation_id()}
    )
    with pytest.raises(DelegationError, match="set by the conductor"):
        conductor.invoke(forged)
    with pytest.raises(DelegationError, match="unknown or expired"):
        conductor.invoke_delegated(request("fake.none"), "not-a-token")

    conductor.invoke(request("fake.delegation", message()))
    with pytest.raises(DelegationError, match="unknown or expired"):
        conductor.invoke_delegated(request("fake.none"), tokens[0])  # the parent has finished


@pytest.mark.requirement("DD-DELEGATION")
def test_self_delegation_and_a_second_level_are_refused(tmp_path: Path) -> None:
    def to_self(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert ctx.delegate is not None
        try:
            ctx.delegate("fake.delegation", message())
        except DelegationRefused as exc:
            return abstain(str(exc))
        raise AssertionError("self-delegation was not refused")

    conductor = make_conductor(tmp_path, ScriptedAgent(GroundingMode.DELEGATION, to_self))
    env = conductor.invoke(request("fake.delegation", message()))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert "may not delegate to itself" in env.outcome.statement

    def second_level(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        if ctx.delegate is None:
            return abstain("No grant at depth 1.")
        return reply_over(ctx, ctx.delegate("fake.inner", message()))

    outer = ScriptedAgent(GroundingMode.DELEGATION, second_level)
    inner = ScriptedAgent(GroundingMode.DELEGATION, second_level, agent_id="fake.inner")
    conductor = make_conductor(tmp_path / "depth", outer, inner)
    env = conductor.invoke(request("fake.delegation", message()))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    child = conductor.store.get(env.delegations[0].delegated_invocation_id)
    assert child is not None
    assert child["outcome"]["statement"] == "No grant at depth 1."


@pytest.mark.requirement("DD-DELEGATION")
def test_a_child_may_not_reuse_its_parents_invocation_id(tmp_path: Path) -> None:
    def reuse_parent_id(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        child = request("fake.none").model_copy(update={"invocation_id": req.invocation_id})
        with pytest.raises(DuplicateInvocation):
            conductor.invoke_delegated(child, grant_token(ctx))
        return abstain("The child was refused.")

    conductor = make_conductor(
        tmp_path, ScriptedAgent(GroundingMode.DELEGATION, reuse_parent_id), child_agent()
    )
    parent = conductor.invoke(request("fake.delegation", message()))
    assert parent.outcome.statement == "The child was refused."
    assert parent.delegations == []
    stored = conductor.store.get(parent.invocation_id)
    assert stored is not None and stored["agent_id"] == "fake.delegation"
    assert [e["invocation_id"] for e in conductor.store.iter_envelopes()] == [parent.invocation_id]


@pytest.mark.requirement("DD-DELEGATION")
@pytest.mark.requirement("DD-POLICY")
def test_a_child_refused_by_policy_is_recorded_and_relayed(tmp_path: Path) -> None:
    conductor = make_conductor(
        tmp_path, delegating("fake.disabled"), child_agent(agent_id="fake.disabled")
    )
    env = conductor.invoke(request("fake.delegation", message()))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    assert env.delegations[0].delegated_status == OutcomeStatus.FAILED
    child = conductor.store.get(env.delegations[0].delegated_invocation_id)
    assert child is not None and "not in agents_enabled" in child["outcome"]["statement"]


@pytest.mark.requirement("DD-DELEGATION")
def test_delegations_are_kept_when_the_parent_fails_after_delegating(tmp_path: Path) -> None:
    def then_raise(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert ctx.delegate is not None
        ctx.delegate("fake.none", record())
        raise RuntimeError("after delegating")

    def then_misground(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert ctx.delegate is not None
        done = ctx.delegate("fake.none", record())
        forged = done.ref.model_copy(update={"content_hash": "0" * 64})
        result = reply_over(ctx, done)
        assert result.payload is not None
        return AgentResult(
            outcome=result.outcome,
            payload=result.payload.model_copy(update={"grounded_on": [forged]}),
            evidence=result.evidence,
        )

    def then_break_the_contract(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert ctx.delegate is not None
        ctx.delegate("fake.none", record())
        return AgentResult(outcome=Outcome(status=OutcomeStatus.ABSTAINED, statement="No reason."))

    for behaviour, status in (
        (then_raise, "failed"),
        (then_misground, "failed"),
        (then_break_the_contract, "failed"),
    ):
        conductor = make_conductor(
            tmp_path / behaviour.__name__,
            ScriptedAgent(GroundingMode.DELEGATION, behaviour),
            child_agent(),
        )
        env = conductor.invoke(request("fake.delegation", message()))
        assert env.outcome.status == status
        assert len(env.delegations) == 1
        assert conductor.store.get(env.invocation_id) is not None
        assert conductor.store.get(env.delegations[0].delegated_invocation_id) is not None


def test_a_child_that_finishes_after_its_parent_is_still_recorded(tmp_path: Path) -> None:
    """The parent does not wait for its child (as when its delegate call times out). The child
    is stored with the parent's id, so the parent's envelope must still list it."""
    admitted, release = threading.Event(), threading.Event()

    def slow_review(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        admitted.set()
        release.wait(timeout=5)
        return review_of_input(req, ctx)

    def fire_and_forget(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        child = request("fake.none", record())
        threading.Thread(target=conductor.invoke_delegated, args=(child, grant_token(ctx))).start()
        admitted.wait(timeout=5)
        # Released only after the parent has returned and reached revocation.
        threading.Timer(0.2, release.set).start()
        return abstain("Did not wait for the child.")

    conductor = make_conductor(
        tmp_path,
        ScriptedAgent(GroundingMode.DELEGATION, fire_and_forget),
        ScriptedAgent(GroundingMode.NONE, slow_review),
    )
    env = conductor.invoke(request("fake.delegation", message()))
    [delegation] = env.delegations
    stored = conductor.store.get(delegation.delegated_invocation_id)
    assert stored is not None and stored["parent_invocation_id"] == env.invocation_id


def test_a_delegation_agent_run_without_a_callback_gets_no_delegate(tmp_path: Path) -> None:
    seen: list[RunContext] = []

    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        seen.append(ctx)
        return abstain("No callback.")

    conductor = make_conductor(tmp_path, ScriptedAgent(GroundingMode.DELEGATION, behaviour))
    conductor.workbench_url = None  # as under `workbench invoke`
    conductor.invoke(request("fake.delegation", message()))
    assert seen[0].delegate is None

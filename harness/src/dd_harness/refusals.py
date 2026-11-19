"""What decides a run before its agent runs (docs/specs/system.md): the first of `REFUSALS`
that applies. In order: the policy gate, the model broker, approval, cancellation, the input
check, the project's facts and the profile's `hosted_models`.

`dd_harness.pipeline`'s `refuse` step runs them, over the run's `RunState`; only the conductor
calls the steps.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dd_harness.observe import cancelled_result
from dd_harness.run_state import RunHost, RunState
from dd_sdk.agent import AgentResult, AgentSpec
from dd_sdk.contract import problem as problems
from dd_sdk.contract.models import (
    Outcome,
    OutcomeStatus,
    ProblemDetails,
    ReasonCode,
)
from dd_sdk.security_log import SecurityEvent, emit

DATA_STEWARD = "data_steward"

type Decided = tuple[AgentResult, ProblemDetails | None]


def refuse(conductor: RunHost, run: RunState) -> None:
    """Decide the run without its agent, by the first of `REFUSALS` that applies."""
    for refusal in REFUSALS:
        if (decided := refusal(conductor, run)) is not None:
            run.result, run.prob = decided
            return


def failed_result(statement: str) -> AgentResult:
    """A failed result, with `statement` saying why."""
    return AgentResult(outcome=Outcome(status=OutcomeStatus.FAILED, statement=statement))


def _not_allowed(conductor: RunHost, run: RunState) -> Decided | None:
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
    return failed_result(f"{decision.reason}. The agent was not run."), prob


def _broker_bypassed(conductor: RunHost, run: RunState) -> Decided | None:
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
    return failed_result(statement), problems.model_broker_bypassed(agent_id, profile_id)


def _needs_approval(conductor: RunHost, run: RunState) -> Decided | None:
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


def _cancelled(conductor: RunHost, run: RunState) -> Decided | None:
    return cancelled_result(run.spec.agent_id, ran=False) if run.watch.cancelled() else None


def _input_refused(conductor: RunHost, run: RunState) -> Decided | None:
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
    return failed_result(f"{statement} The agent was not run."), prob


def _unfillable(conductor: RunHost, run: RunState) -> Decided | None:
    """3. Project facts: the document a redraft names must be one of the project's, of the kind
    asked for (docs/specs/projects.md, invariant 6)."""
    if run.unfillable is None:
        return None
    statement = f"{run.unfillable}. The agent was not run."
    return failed_result(statement), problems.revision_refused(run.unfillable)


def _kept_back(conductor: RunHost, run: RunState) -> Decided | None:
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
    return failed_result(statement), prob


# In order: the first that applies decides the run, and its agent is not run.
REFUSALS: tuple[Callable[[RunHost, RunState], Decided | None], ...] = (
    _not_allowed,
    _broker_bypassed,
    _needs_approval,
    _cancelled,
    _input_refused,
    _unfillable,
    _kept_back,
)


def input_refusal(spec: AgentSpec, document: dict[str, Any]) -> tuple[str, list[str]] | None:
    """Why the agent will not read this input: the class it names, and how the input fails that
    class's schema (no errors: the agent does not accept the class at all). None if it will."""
    got = str(document.get("schema_class"))
    accepted = spec.accepted(got)
    if accepted is None:
        return got, []
    errors = accepted.errors(document)
    return (got, errors) if errors else None

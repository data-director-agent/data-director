"""What people in the project decided, read into the context (`given.py`, docs/specs/projects.md
invariant 6): each decided funder is an actor whose policy is looked up, whether or not the
caller named it, and one the caller named is not added twice. The conductor fills the decisions in
a project; here they are sent as a caller outside a project would, which the agent reads the same
way."""

from __future__ import annotations

from pathlib import Path

from test_policy_agent import invoke

from dd_agent_advisor_policy import given
from dd_agent_advisor_policy.classes import Actor, ActorRole, PolicyChecks, PolicyContext
from dd_sdk.contract.facts import ProjectFact
from dd_sdk.contract.models import OutcomeStatus

FUNDER = "Social Research Council"


def funder(name: str = FUNDER, ror: str | None = None) -> ProjectFact:
    return ProjectFact(
        fact_kind="funder", fact_subject=name, fact_funder_name=name, fact_funder_ror=ror
    )


def test_a_decided_funder_is_looked_up_when_the_caller_named_none(runs_dir: Path) -> None:
    env = invoke(runs_dir, PolicyContext(project_decisions=[funder()]))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert [p.actor for p in env.payload_as(PolicyChecks).policies] == [FUNDER]


def test_a_funder_the_caller_named_is_not_added_twice() -> None:
    named = Actor(role=ActorRole.FUNDER, name=FUNDER.upper())
    context = PolicyContext(actors=[named], project_decisions=[funder()])
    assert given.with_project(context).actors == [named]


def test_a_decided_funder_keeps_its_ror_identifier_when_the_actor_can_hold_it() -> None:
    ror = "https://ror.org/02b5d8509"
    (actor,) = given.with_project(PolicyContext(project_decisions=[funder(ror=ror)])).actors
    assert (actor.role, actor.ror_id) == (ActorRole.FUNDER, ror)
    (bare,) = given.with_project(PolicyContext(project_decisions=[funder(ror="nope")])).actors
    assert bare.ror_id is None

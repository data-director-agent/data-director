"""What people in the project decided, read into the context (docs/specs/projects.md,
invariant 6).

In a project the conductor gives `PolicyContext` the facts people decided. A person's decision
takes precedence over what the caller wrote: each decided funder is an actor whose policy is
looked up, whether or not the caller named it, with its ROR identifier where the decision holds
one. A funder the caller already named, by ROR identifier or by name, is not added twice.
Outside a project the caller's context stands as sent.
"""

from __future__ import annotations

from pydantic import ValidationError

from dd_agent_advisor_policy.classes import Actor, ActorRole, PolicyContext
from dd_sdk.contract.facts import FactKind, ProjectFact


def with_project(context: PolicyContext) -> PolicyContext:
    """The context with each decided funder among its actors."""
    actors = list(context.actors)
    for fact in context.project_decisions:
        if fact.fact_kind != FactKind.FUNDER or not fact.fact_funder_name:
            continue
        funder = _funder(fact)
        if not any(_same(funder, actor) for actor in actors):
            actors.append(funder)
    if len(actors) == len(context.actors):
        return context
    return context.model_copy(update={"actors": actors})


def _funder(fact: ProjectFact) -> Actor:
    """A decided funder as an actor; a ROR identifier the actor cannot hold is left out, so the
    funder is looked up by name instead."""
    name = str(fact.fact_funder_name)
    try:
        return Actor(role=ActorRole.FUNDER, name=name, ror_id=fact.fact_funder_ror)
    except ValidationError:
        return Actor(role=ActorRole.FUNDER, name=name)


def _same(a: Actor, b: Actor) -> bool:
    if a.role != b.role:
        return False
    if a.ror_id and b.ror_id:
        return a.ror_id.rsplit("/", 1)[-1] == b.ror_id.rsplit("/", 1)[-1]
    return a.name.casefold() == b.name.casefold()

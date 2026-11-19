"""What people in the project decided, read into the context (docs/specs/projects.md,
invariant 6).

In a project the conductor gives `RightsContext` the facts people decided. A person's decision
takes precedence over what the caller wrote: a decided licence is the mandated licence. A decision
to withhold or generalise a sensitive field or file says the data are sensitive, where the caller
left that unknown; a decision to publish one says nothing about the rest, so it is not read.
Outside a project the caller's context stands as sent.
"""

from __future__ import annotations

from dd_agent_advisor_rights.classes import RightsContext
from dd_sdk.contract.facts import FactKind, SensitivityDecision

# Decisions that hold back some of the data, so the data are sensitive.
HELD_BACK = frozenset({SensitivityDecision.WITHHOLD, SensitivityDecision.GENERALISE})


def with_project(context: RightsContext) -> RightsContext:
    """The context with what people in the project decided in place of the caller's."""
    update: dict[str, object] = {}
    for fact in context.project_decisions:
        if fact.fact_kind == FactKind.LICENCE and fact.licence_id:
            update["mandated_licence"] = fact.licence_id
        if (
            fact.fact_kind == FactKind.SENSITIVITY
            and fact.sensitivity_decision in HELD_BACK
            and context.sensitive is None
        ):
            update["sensitive"] = True
    return context.model_copy(update=update) if update else context

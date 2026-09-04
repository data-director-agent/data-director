"""RFC 9457 problem types the harness emits (ADR-0004).

Type URIs are under a w3id namespace that is not yet registered. TODO: register
https://w3id.org/data-director/ or move to a namespace the project controls.
"""

from __future__ import annotations

from workbench.contract.models import ProblemDetails

PROBLEM_BASE = "https://w3id.org/data-director/problems/"


def problem(slug: str, title: str, detail: str, http_status: int = 500) -> ProblemDetails:
    return ProblemDetails(
        type=PROBLEM_BASE + slug, title=title, detail=detail, http_status=http_status
    )


def agent_not_permitted(agent_id: str, profile_id: str) -> ProblemDetails:
    return problem(
        "agent-not-permitted",
        "Agent not enabled by the institutional profile",
        f"Agent {agent_id!r} is not listed in agents_enabled of profile {profile_id!r}.",
        http_status=403,
    )


def grounding_violation(violations: list[str]) -> ProblemDetails:
    return problem(
        "grounding-violation",
        "Output failed the grounding linter",
        "Nothing ungrounded leaves the system. Violations: " + "; ".join(violations),
    )


def agent_error(agent_id: str, exc: BaseException) -> ProblemDetails:
    return problem(
        "agent-error",
        "Agent raised an exception",
        f"{agent_id}: {type(exc).__name__}: {exc}",
    )

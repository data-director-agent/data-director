"""RFC 9457 problem types the harness emits (docs/specs/contract.md).

Type URIs are under a w3id namespace that is not yet registered. TODO(#3): register
https://w3id.org/data-director/ or move to a namespace the project controls.
"""

from __future__ import annotations

from dd_sdk.contract.models import ProblemDetails

PROBLEM_BASE = "https://w3id.org/data-director/problems/"


def problem(slug: str, title: str, detail: str, http_status: int = 500) -> ProblemDetails:
    return ProblemDetails(
        type=PROBLEM_BASE + slug, title=title, detail=detail, http_status=http_status
    )


def agent_not_permitted(agent_id: str, profile_id: str) -> ProblemDetails:
    return problem(
        "agent-not-permitted",
        "Agent not enabled by the institutional profile",
        f"Agent {agent_id!r} is not listed in agents of profile {profile_id!r}.",
        http_status=403,
    )


def action_class_mismatch(
    agent_id: str, declared: str, assigned: str, profile_id: str
) -> ProblemDetails:
    return problem(
        "action-class-mismatch",
        "Agent declares an action class the institutional profile does not assign it",
        f"Agent {agent_id!r} declares {declared!r}; profile {profile_id!r} assigns it "
        f"{assigned!r}. The steward must update the profile before this agent runs.",
        http_status=403,
    )


def unauthenticated(detail: str) -> ProblemDetails:
    """A caller whose credential is missing or bad (docs/specs/policy-and-identity.md). `detail`
    never holds the credential."""
    return problem("unauthenticated", "The caller is not signed in", detail, http_status=401)


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


def input_not_accepted(
    agent_id: str, got: str, accepts: tuple[str, ...], errors: tuple[str, ...] = ()
) -> ProblemDetails:
    """The agent does not read `got`, or `errors` says how the input fails that class's schema."""
    if errors:
        detail = (
            f"Agent {agent_id!r} accepts {got!r}, but the input does not conform to its schema: "
            + "; ".join(errors)
        )
    else:
        detail = (
            f"Agent {agent_id!r} accepts {', '.join(accepts) or 'nothing'}; the request carried "
            f"{got!r}."
        )
    return problem(
        "input-not-accepted", "Agent does not accept this input", detail, http_status=422
    )


def project_content_withheld(
    agent_id: str, classes: tuple[str, ...], profile_id: str
) -> ProblemDetails:
    return problem(
        "project-content-withheld",
        "Project content the profile keeps from hosted models",
        f"Agent {agent_id!r} calls a hosted model, and hosted_models of profile {profile_id!r} "
        f"does not list {', '.join(classes)}. Nothing was sent to the agent.",
        http_status=403,
    )


def revision_refused(detail: str) -> ProblemDetails:
    """A drafted document the project could not record: it revises no version of the project, or
    a version of a document of another kind (docs/specs/projects.md)."""
    return problem("revision-refused", "The draft does not revise this project", detail, 409)

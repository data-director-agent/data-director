"""A project's facts: what check agents proposed, and a person's decisions on them
(docs/specs/projects.md).

`GET /api/projects/{id}/facts` reads the proposals nobody has decided yet and the facts that stand.
`POST /api/projects/{id}/facts/decisions` records a person's decision. The body is
`{"verdict": "confirmed" | "changed" | "rejected", "proposal"?, "fact"?, "reason"?}`: `confirmed`
names a proposal and takes it as it is, `changed` gives the person's own `ProjectFact`, for a
proposal's kind and subject or for one nobody proposed, and `rejected` names a proposal or a
fact's kind and subject. A decision on a proposal the project does not hold is answered `404`;
one on a proposal a later proposal or decision on its kind and subject has followed, and a changed
fact of another kind or subject than its proposal's, `409`. Members may decide
funders, required repositories and which files go in; whether sensitive data may be published,
and the licence, have legal consequences, so only an owner may decide them. Who decided is whom
the authenticator names, never the body.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import MISSING
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app import contract_shapes as contract
from dd_app.routes.common import (
    Deps,
    RequestBody,
    ResponseBody,
    caused_by,
    in_project,
    parse_body,
    problem,
    project_refused,
    respond,
)
from dd_harness.project_access import Action, allowed
from dd_harness.projects import ChangeRefusedError, FactVerdict, ProjectError, Refusal
from dd_sdk.contract.facts import FactKind
from dd_sdk.contract.models import Principal

FACT_REFUSED = "Data Director could not record this decision"
# The kinds of fact only an owner may decide (docs/specs/projects.md).
OWNERS_FACTS = frozenset({FactKind.SENSITIVITY.value, FactKind.LICENCE.value})


class DecideFact(RequestBody):
    """A person's decision on a proposed fact, or a fact they state. What it may hold together is
    the project rules' to check (`dd_harness.projects.facts`)."""

    refusal: ClassVar[str] = (
        "`verdict` is confirmed, changed or rejected; `proposal` names a proposal; `fact` is a "
        "ProjectFact; `reason` is text."
    )

    verdict: Literal["confirmed", "changed", "rejected"]
    proposal: str | None = None
    fact: dict[str, Any] | None = None
    reason: str | None = None


class FactProposal(ResponseBody):
    """A proposal no decision on its kind and subject has followed yet."""

    proposal: str
    """The proposal's identifier, which a decision names."""
    agent_id: str
    """The check agent that proposed it."""
    proposed_at: str
    fact: contract.ProjectFact
    """The fact as proposed, with why (`proposed_because`), for the person deciding."""


class ProjectFacts(ResponseBody):
    """What a project holds: proposals to decide, and the facts that stand."""

    proposals: list[FactProposal]
    decisions: list[contract.ProjectFact]
    """The facts that stand: the last decision on each kind and subject."""
    decided: contract.ProjectFact | MISSING | None = MISSING
    """After a decision, the fact that now stands, or null after a rejection."""


def routes(deps: Deps) -> list[Route]:
    facts = "/api/projects/{project_id}/facts"
    return [
        Route(facts, in_project(deps, Action.READ, get_facts), methods=["GET"]),
        Route(
            f"{facts}/decisions",
            in_project(deps, Action.CONTRIBUTE, decide_fact),
            methods=["POST"],
        ),
    ]


async def get_facts(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    return respond(ProjectFacts, await run_in_threadpool(deps.projects.facts, project_id))


async def decide_fact(request: Request, decider: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    body = await parse_body(request, DecideFact, FACT_REFUSED)
    if isinstance(body, Response):
        return body
    kind = await run_in_threadpool(_kind, deps, project_id, body.proposal, body.fact)
    if kind in OWNERS_FACTS:
        role = await run_in_threadpool(deps.governance.role, project_id, decider)
        if role is None or not allowed(role, Action.DECIDE):
            return problem(
                403,
                "project-action-forbidden",
                "Not yours to do in this project",
                f"Only an owner of project {project_id!r} may decide a {kind} fact.",
            )
    try:
        decided = await run_in_threadpool(
            lambda: deps.projects.decide_fact(
                project_id,
                FactVerdict(body.verdict),
                proposal=body.proposal,
                fact=body.fact,
                reason=body.reason,
                acted_for=decider,
                caused_by=caused_by(request),
            )
        )
    except ProjectError as exc:
        return _change_refused(exc, project_id)
    return respond(ProjectFacts, decided, status_code=201)


def _kind(
    deps: Deps, project_id: str, proposal: str | None, fact: dict[str, Any] | None
) -> str | None:
    """The kind of fact a decision is about: the fact's own, or its proposal's."""
    if fact is not None and fact.get("fact_kind") is not None:
        return str(fact["fact_kind"])
    return None if proposal is None else deps.projects.proposed_kind(project_id, proposal)


def _change_refused(exc: ProjectError, project_id: str) -> Response:
    """`404` for a proposal that is not there, `409` for a proposal a later proposal or decision
    has followed or a fact that is not the proposal's, and `400` for a decision the project
    refuses."""
    if isinstance(exc, ChangeRefusedError):
        if exc.refusal is Refusal.NO_PROPOSAL:
            return problem(404, exc.refusal.value, "No such proposal", exc.detail)
        if exc.refusal is Refusal.SUPERSEDED:
            return problem(409, exc.refusal.value, "Proposal already decided", exc.detail)
        return problem(409, exc.refusal.value, "Not the fact proposed", exc.detail)
    return project_refused(exc, project_id, FACT_REFUSED)

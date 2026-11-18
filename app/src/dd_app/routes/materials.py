"""What a project holds of the researcher's files and of the researcher (docs/specs/projects.md).

`GET /api/projects/{id}/inventory` is the inventory the project holds, as it was added, for the
researcher to read; it answers `404` when there is none. `POST /api/projects/{id}/inventory` adds
`{"inventory": …}` to the project as its latest, for the person signed in: the researcher's
revision of the one it holds, or a new scan. It answers `201` with what the project then holds of
it. `GET /api/projects/{id}/documentation` lists the documents attached to the project, without
their text, and `GET /api/projects/{id}/documentation/{digest}` is one document's text, `404` when
the project holds none with that digest. `GET /api/researcher/orcid` is the signed-in person's
public ORCID record, and `…/researchers` what of it they kept in a project.
"""

from __future__ import annotations

from typing import Any, ClassVar

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from dd_app import contract_shapes as contract
from dd_app.routes.common import (
    Deps,
    Endpoint,
    Handler,
    RequestBody,
    caused_by,
    in_project,
    parse_body,
    problem,
    project_refused,
    respond,
    signed_in,
)
from dd_app.routes.projects import SavedInventory
from dd_harness import orcid
from dd_harness.project_access import Action
from dd_harness.projects import ProjectError, UnknownProjectError
from dd_sdk.contract.models import Principal, now

INVENTORY_REFUSED = "Data Director could not add this inventory"
RESEARCHER_REFUSED = "Data Director could not keep these ORCID facts"


class AddInventory(RequestBody):
    """A revised or new inventory; the store checks it against the `FileInventory` class."""

    refusal: ClassVar[str] = "`inventory` must be the object `dd-inventory` wrote."

    inventory: dict[str, Any]


class KeepResearcher(RequestBody):
    """Which of their public ORCID record the person ticked
    (`{"keep": {"sections": [...], "works": [put-codes], ...}}`), never the facts themselves."""

    refusal: ClassVar[str] = "`keep` names the sections and items to keep."

    keep: dict[str, Any]


def routes(deps: Deps) -> list[Route]:
    def read(handler: Handler) -> Endpoint:
        return in_project(deps, Action.READ, handler)

    def contribute(handler: Handler) -> Endpoint:
        return in_project(deps, Action.CONTRIBUTE, handler)

    project = "/api/projects/{project_id}"
    return [
        Route(f"{project}/inventory", read(get_inventory), methods=["GET"]),
        Route(f"{project}/inventory", contribute(add_inventory), methods=["POST"]),
        Route(f"{project}/documentation", read(list_documentation), methods=["GET"]),
        Route(f"{project}/documentation/{{digest}}", read(get_documentation), methods=["GET"]),
        Route(f"{project}/researchers", read(list_researchers), methods=["GET"]),
        Route(f"{project}/researchers/me", contribute(keep_researcher), methods=["PUT"]),
        Route(f"{project}/researchers/me", contribute(withdraw_researcher), methods=["DELETE"]),
        Route("/api/researcher/orcid", signed_in(deps, get_orcid_record), methods=["GET"]),
    ]


async def get_inventory(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(deps.projects.inventory, project_id)
    if found is None:
        return problem(
            404, "inventory-not-found", "No inventory", f"Project {project_id!r} has none."
        )
    return respond(contract.FileInventory, found)


async def add_inventory(request: Request, person: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    body = await parse_body(request, AddInventory, INVENTORY_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        held = await run_in_threadpool(
            lambda: deps.projects.add_inventory(
                project_id, body.inventory, acted_for=person, caused_by=f"POST {request.url.path}"
            )
        )
    except ProjectError as exc:
        return project_refused(exc, project_id, INVENTORY_REFUSED)
    return respond(SavedInventory, held, status_code=201)


async def list_documentation(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    return respond(
        list[contract.DocumentationSummary],
        await run_in_threadpool(deps.projects.documentation, project_id),
    )


async def get_documentation(request: Request, _: Principal, deps: Deps) -> Response:
    project_id, digest = request.path_params["project_id"], request.path_params["digest"]
    found = await run_in_threadpool(deps.projects.documentation_text, project_id, digest)
    if found is None:
        return problem(
            404,
            "documentation-not-found",
            "No such document",
            f"Project {project_id!r} holds no document {digest!r}.",
        )
    return PlainTextResponse(found)


def read_orcid(person: Principal, deps: Deps) -> dict[str, Any]:
    """`person`'s own public ORCID record as a `ResearcherRecord`: only their own iD is ever
    read, and only when they ask (docs/specs/policy-and-identity.md)."""
    issuer = orcid.issuer_of(person)
    raw = orcid.fetch_record(person.principal_id, issuer, transport=deps.orcid_transport)
    return orcid.normalise(
        raw,
        principal_id=person.principal_id,
        retrieved_at=now(),
        source=orcid.record_url(person.principal_id, issuer),
    )


async def get_orcid_record(request: Request, person: Principal, deps: Deps) -> Response:
    """What the signed-in person's public ORCID record offers, to choose from. Nothing is
    kept: keeping is `keep_researcher`, which reads the record again."""
    try:
        return respond(contract.ResearcherRecord, await run_in_threadpool(read_orcid, person, deps))
    except orcid.OrcidError as exc:
        return problem(409, "no-orcid-record", "No ORCID record to read", str(exc))
    except orcid.OrcidUnavailableError as exc:
        return _orcid_unavailable(str(exc))


async def list_researchers(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    return respond(
        list[contract.ResearcherRecord],
        await run_in_threadpool(deps.projects.researchers, project_id),
    )


async def keep_researcher(request: Request, person: Principal, deps: Deps) -> Response:
    """Keep in the project what the person ticked of their own public ORCID record. The record
    is read again and only what it holds is kept, so the project holds ORCID's own words.
    Answers with the project's records."""
    project_id = request.path_params["project_id"]
    body = await parse_body(request, KeepResearcher, RESEARCHER_REFUSED)
    if isinstance(body, Response):
        return body
    cause = caused_by(request)

    def keep() -> list[dict[str, Any]]:
        chosen = orcid.select(read_orcid(person, deps), body.keep)
        return deps.projects.keep_researcher(project_id, chosen, acted_for=person, caused_by=cause)

    try:
        return respond(
            list[contract.ResearcherRecord], await run_in_threadpool(keep), status_code=201
        )
    except UnknownProjectError:
        raise
    except orcid.OrcidUnavailableError as exc:
        return _orcid_unavailable(str(exc))
    except (orcid.OrcidError, ProjectError) as exc:
        return problem(400, "request-refused", RESEARCHER_REFUSED, str(exc))


async def withdraw_researcher(request: Request, person: Principal, deps: Deps) -> Response:
    """Stop giving agents the ORCID facts the person kept in the project. Answers with the
    project's records that stand."""
    project_id = request.path_params["project_id"]
    try:
        standing = await run_in_threadpool(
            lambda: deps.projects.withdraw_researcher(
                project_id, acted_for=person, caused_by=caused_by(request)
            )
        )
    except UnknownProjectError:
        raise
    except ProjectError as exc:
        return problem(404, "researcher-not-found", "Nothing of yours to withdraw", str(exc))
    return respond(list[contract.ResearcherRecord], standing)


def _orcid_unavailable(detail: str) -> Response:
    return problem(502, "orcid-unavailable", "ORCID could not be reached", detail)

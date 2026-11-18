"""What a project holds of the researcher's files and of the researcher (docs/specs/projects.md).

`GET /api/projects/{id}/inventory` is the inventory the project holds, as it was added, for the
researcher to read; it answers `404` when there is none. `POST /api/projects/{id}/inventory` adds
`{"inventory": …}` to the project as its latest, for the person signed in: the researcher's
revision of the one it holds, or a new scan. It answers `201` with what the project then holds of
it. `GET /api/projects/{id}/documentation` lists the documents attached to the project, without
their text, and `GET /api/projects/{id}/documentation/{digest}` is one document's text, `404` when
the project holds none with that digest; with `?original`, the Word document or PDF its text was
read from, `404` for one attached as text. `POST /api/documentation/extract` reads the text of a
Word document or PDF (`{"name", "media_type", "data"}`, the file as base64) for the person to
check before they attach it, and keeps nothing (#961). `GET /api/researcher/orcid` is the
signed-in person's public ORCID record, and `…/researchers` what of it they kept in a project.
"""

from __future__ import annotations

from typing import Any, ClassVar

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from dd_app.problems import refused
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
    signed_in,
)
from dd_app.turn_body import decoded
from dd_harness import orcid
from dd_harness.policy import check_attached_document
from dd_harness.project_access import Action
from dd_harness.projects import ProjectError, UnknownProjectError, read_document_file
from dd_sdk.contract.models import Principal, now

INVENTORY_REFUSED = "Data Director could not add this inventory"
RESEARCHER_REFUSED = "Data Director could not keep these ORCID facts"
DOCUMENT_REFUSED = "Data Director could not read this document"


class AddInventory(RequestBody):
    """A revised or new inventory; the store checks it against the `FileInventory` class."""

    refusal: ClassVar[str] = "`inventory` must be the object `dd-inventory` wrote."

    inventory: dict[str, Any]


class ExtractDocument(RequestBody):
    """A Word document or PDF to read before it is attached: its file name, media type and bytes
    as base64."""

    refusal: ClassVar[str] = (
        "`name`, `media_type` and `data` (the file as base64) must each be a string."
    )

    name: str
    media_type: str
    data: str


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
        Route("/api/documentation/extract", signed_in(deps, extract_document), methods=["POST"]),
    ]


async def get_inventory(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(deps.projects.inventory, project_id)
    if found is None:
        return problem(
            404, "inventory-not-found", "No inventory", f"Project {project_id!r} has none."
        )
    return JSONResponse(found)


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
    return JSONResponse(held, status_code=201)


async def list_documentation(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    return JSONResponse(await run_in_threadpool(deps.projects.documentation, project_id))


async def get_documentation(request: Request, _: Principal, deps: Deps) -> Response:
    project_id, digest = request.path_params["project_id"], request.path_params["digest"]
    if "original" in request.query_params:
        source = await run_in_threadpool(deps.projects.documentation_source, project_id, digest)
        if source is None:
            return problem(
                404,
                "documentation-not-found",
                "No such file",
                f"Project {project_id!r} holds no file its document {digest!r} was read from.",
            )
        return Response(source[0], media_type=source[1])
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
        return JSONResponse(await run_in_threadpool(read_orcid, person, deps))
    except orcid.OrcidError as exc:
        return problem(409, "no-orcid-record", "No ORCID record to read", str(exc))
    except orcid.OrcidUnavailableError as exc:
        return _orcid_unavailable(str(exc))


async def list_researchers(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    return JSONResponse(await run_in_threadpool(deps.projects.researchers, project_id))


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
        return JSONResponse(await run_in_threadpool(keep), status_code=201)
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
    return JSONResponse(standing)


def _orcid_unavailable(detail: str) -> Response:
    return problem(502, "orcid-unavailable", "ORCID could not be reached", detail)


async def extract_document(request: Request, _: Principal, deps: Deps) -> Response:
    """The text of a Word document or PDF, for the person to check before attaching it."""
    body = await parse_body(request, ExtractDocument, DOCUMENT_REFUSED)
    if isinstance(body, Response):
        return body
    data = decoded(body.data)
    if data is None:
        return refused("`data` must be the file, encoded as base64.", DOCUMENT_REFUSED)
    try:
        check_attached_document(deps.governance.conductor.profile)
        text = await run_in_threadpool(read_document_file, body.name, body.media_type, data)
    except ValueError as exc:  # a `ProjectError`, or documents the profile refuses
        return refused(str(exc), DOCUMENT_REFUSED)
    return JSONResponse({"name": body.name, "text": text, "size": len(text.encode("utf-8"))})

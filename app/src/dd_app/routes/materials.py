"""What a project holds of the researcher's files and of the researcher (docs/specs/projects.md).

`GET /api/projects/{id}/inventory` is the inventory the project holds, as it was added, for the
researcher to read; it answers `404` when there is none. `POST /api/projects/{id}/inventory` adds
`{"inventory": …}` to the project as its latest, for the person signed in: the researcher's
revision of the one it holds, or a new scan. It answers `201` with what the project then holds of
it. `GET /api/projects/{id}/documentation` lists the documents attached to the project, without
their text; `POST /api/projects/{id}/documentation` attaches one outside a conversation, as a turn
does (`{"name", "media_type", "text"}`, or `{"name", "media_type", "data"}` for a Word document or
PDF, and the `confirmed` kinds of possible personal data the person has checked), answering `201`
with the documents the project then holds, `409` when what was found is not confirmed and `400`
when the profile or the project refuses it; and `GET /api/projects/{id}/documentation/{digest}`
is one document's text, `404` when the project holds none with that digest; with `?original`,
the Word document or PDF its text was read from, `404` for one attached as text; with `?preview`,
a copy to read, which is the stored text under its media type except for a Word document, whose
text is read again from the file as Markdown, so that one attached before Word documents were read
as Markdown is laid out as well. A preview keeps nothing and is not what agents read.
`POST /api/documentation/extract` reads the text of a Word document or PDF
(`{"name", "media_type", "data"}`, the file as base64) for the person to check before they attach
it, and keeps nothing (#961). `POST /api/documentation/check` checks a
document's text for possible personal data and secrets before it is attached, in or out of a
project, keeping nothing: it answers with what was found, by kind, never a value (#473).
`GET /api/researcher/orcid` is the signed-in person's public ORCID record, and `…/researchers`
what of it they kept in a project.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import MISSING, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from dd_app import contract_shapes as contract
from dd_app.documentation_check import DocumentationHeldError, checked_with, kinds, screen
from dd_app.problems import refused
from dd_app.routes.common import (
    Deps,
    Endpoint,
    Handler,
    RequestBody,
    ResponseBody,
    caused_by,
    in_project,
    parse_body,
    problem,
    project_refused,
    respond,
    signed_in,
)
from dd_app.routes.conversations import SavedInventory
from dd_app.turn_body import AttachedDocument, decoded
from dd_harness import orcid
from dd_harness.policy import check_attached_document
from dd_harness.project_access import Action
from dd_harness.projects import (
    ProjectError,
    UnknownProjectError,
    check_documentation,
    read_document_file,
)
from dd_harness.projects.extract import DOCX, extract_text, extracted_media_type
from dd_sdk.contract.models import Principal, now

INVENTORY_REFUSED = "Data Director could not add this inventory"
CHECK_REFUSED = "Data Director could not check this document"
RESEARCHER_REFUSED = "Data Director could not keep these ORCID facts"
DOCUMENT_REFUSED = "Data Director could not read this document"
DOCUMENT_ATTACH_REFUSED = "Data Director could not attach this document"


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


class AttachDocument(RequestBody):
    """A document to keep in the project: its file name, media type and text, or, for a Word
    document or PDF, the file as base64 (the server reads its text), and the kinds of possible
    personal data or secrets the person confirmed it holds."""

    refusal: ClassVar[str] = (
        "Give the document's `name` and `media_type`, and its `text` or, for a Word document "
        "or PDF, its `data` as base64; `confirmed` lists the kinds found that you checked."
    )

    name: str
    media_type: str
    text: str | None = None
    data: str | None = None
    confirmed: list[str] = Field(default_factory=list)


class CheckDocument(RequestBody):
    """A document to check before it is attached: its file name, media type and text."""

    refusal: ClassVar[str] = "Give the document's `name`, `media_type` and `text`, as strings."

    name: str
    media_type: str
    text: str


class DocumentFinding(ResponseBody):
    """What may be in a document: a kind of personal data, or `secret` with the type of secret as
    its detail."""

    kind: str
    places: str
    """How many places, as a band, so that a finding cannot be turned into a count."""
    confidence: str
    detail: str | MISSING = MISSING
    """The type of secret; left out for personal data."""


class DocumentCheck(ResponseBody):
    """What the check found in a document before it is attached (`POST /api/documentation/check`)"""

    findings: list[DocumentFinding]
    kinds: list[str]
    """The kinds a researcher confirms: a secret's type stands for itself."""
    checked_with: str
    """What the check ran."""


class ExtractedDocument(ResponseBody):
    """The text read from a Word document or PDF (`POST /api/documentation/extract`)."""

    name: str
    text: str
    size: int
    """The text's length in bytes, as UTF-8."""


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
        Route(f"{project}/documentation", contribute(add_documentation), methods=["POST"]),
        Route(f"{project}/documentation/{{digest}}", read(get_documentation), methods=["GET"]),
        Route(f"{project}/researchers", read(list_researchers), methods=["GET"]),
        Route(f"{project}/researchers/me", contribute(keep_researcher), methods=["PUT"]),
        Route(f"{project}/researchers/me", contribute(withdraw_researcher), methods=["DELETE"]),
        Route("/api/researcher/orcid", signed_in(deps, get_orcid_record), methods=["GET"]),
        Route("/api/documentation/extract", signed_in(deps, extract_document), methods=["POST"]),
        Route("/api/documentation/check", signed_in(deps, check_document), methods=["POST"]),
    ]


async def check_document(request: Request, _: Principal, __: Deps) -> Response:
    """What may be in a document before it is attached; nothing is kept and its text is not
    logged. A document the project would refuse anyway is refused here first."""
    body = await parse_body(request, CheckDocument, CHECK_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        check_documentation(body.name, body.media_type, body.text)
    except ProjectError as exc:
        return problem(400, "request-refused", CHECK_REFUSED, str(exc))
    found = await run_in_threadpool(screen, body.text)
    return respond(
        DocumentCheck,
        {
            "findings": [f.as_json() for f in found],
            "kinds": kinds(found),
            "checked_with": await run_in_threadpool(checked_with),
        },
    )


async def get_inventory(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(deps.projects.materials.inventory, project_id)
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
            lambda: deps.projects.materials.add_inventory(
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
        await run_in_threadpool(deps.projects.materials.documentation, project_id),
    )


def attached_document(body: AttachDocument) -> AttachedDocument | Response:
    """The document `body` attaches, or the `400` problem that refuses its shape."""
    if (body.text is None) == (body.data is None):
        return refused("Give either `text` or `data`, not both.", DOCUMENT_ATTACH_REFUSED)
    data = None if body.data is None else decoded(body.data)
    if body.data is not None and data is None:
        return refused("`data` must be the file, encoded as base64.", DOCUMENT_ATTACH_REFUSED)
    return AttachedDocument(
        body.name, body.media_type, body.text or "", data=data, confirmed=tuple(body.confirmed)
    )


async def add_documentation(request: Request, person: Principal, deps: Deps) -> Response:
    """Attach a document to the project outside a conversation. It is checked as a turn's is:
    the profile must allow it, the project must keep one of its kind, and what the personal-data
    check finds must be confirmed. Nothing is kept otherwise."""
    project_id = request.path_params["project_id"]
    body = await parse_body(request, AttachDocument, DOCUMENT_ATTACH_REFUSED)
    if isinstance(body, Response):
        return body
    document = attached_document(body)
    if isinstance(document, Response):
        return document
    cause = caused_by(request)
    try:
        check_attached_document(deps.governance.conductor.profile)
        held = await run_in_threadpool(
            lambda: deps.projects.materials.add_documentation(
                project_id, document, acted_for=person, caused_by=cause
            )
        )
    except DocumentationHeldError as exc:
        title = "This document needs your confirmation"
        return problem(409, "documentation-held", title, str(exc), kinds=exc.kinds)
    except ProjectError as exc:
        return project_refused(exc, project_id, DOCUMENT_ATTACH_REFUSED)
    except ValueError as exc:  # a profile that refuses attached documents
        return refused(str(exc), DOCUMENT_ATTACH_REFUSED)
    return respond(list[contract.DocumentationSummary], held, status_code=201)


def documentation_preview(deps: Deps, project_id: str, digest: str) -> tuple[str, str] | None:
    """The text of the project's document `digest` to read and its media type, or None: the
    stored text, or, for a Word document, its file read again as Markdown."""
    materials = deps.projects.materials
    source = materials.documentation_source(project_id, digest)
    if source is not None and source[1] == DOCX:
        return extract_text(DOCX, source[0]), extracted_media_type(DOCX)
    text = materials.documentation_text(project_id, digest)
    if text is None:
        return None
    held = (d for d in materials.documentation(project_id) if d["documentation_digest"] == digest)
    summary = next(held, {})
    return text, summary.get("documentation_media_type", "text/plain")


async def get_documentation(request: Request, _: Principal, deps: Deps) -> Response:
    project_id, digest = request.path_params["project_id"], request.path_params["digest"]
    if "preview" in request.query_params:
        return await _preview(deps, project_id, digest)
    if "original" in request.query_params:
        return await _original(deps, project_id, digest)
    found = await run_in_threadpool(deps.projects.materials.documentation_text, project_id, digest)
    if found is None:
        return _no_documentation(project_id, digest)
    return PlainTextResponse(found)


async def _preview(deps: Deps, project_id: str, digest: str) -> Response:
    try:
        preview = await run_in_threadpool(documentation_preview, deps, project_id, digest)
    except ProjectError as exc:  # a file this deployment can no longer read
        return refused(str(exc), DOCUMENT_REFUSED)
    if preview is None:
        return _no_documentation(project_id, digest)
    return PlainTextResponse(preview[0], media_type=preview[1])


async def _original(deps: Deps, project_id: str, digest: str) -> Response:
    source = await run_in_threadpool(
        deps.projects.materials.documentation_source, project_id, digest
    )
    if source is None:
        return problem(
            404,
            "documentation-not-found",
            "No such file",
            f"Project {project_id!r} holds no file its document {digest!r} was read from.",
        )
    return Response(source[0], media_type=source[1])


def _no_documentation(project_id: str, digest: str) -> Response:
    return problem(
        404,
        "documentation-not-found",
        "No such document",
        f"Project {project_id!r} holds no document {digest!r}.",
    )


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
        await run_in_threadpool(deps.projects.materials.researchers, project_id),
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
        return deps.projects.materials.keep_researcher(
            project_id, chosen, acted_for=person, caused_by=cause
        )

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
            lambda: deps.projects.materials.withdraw_researcher(
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
    return respond(
        ExtractedDocument,
        {"name": body.name, "text": text, "size": len(text.encode("utf-8"))},
    )

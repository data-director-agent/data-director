"""The approved metadata record converted to another standard (docs/specs/metadata-standards.md,
invariant 9): converting it, the conversions kept, and each one's bytes. A conversion is a
package derived from the approved record, never a document; one that would leave a field the
target requires empty is refused with what to add."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import ConfigDict
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app.project_service import RepositoriesUnavailableError
from dd_app.routes import common
from dd_app.routes.common import Deps, RequestBody, ResponseBody, in_project, parse_body, respond
from dd_harness.conversion import ConversionError, Converted
from dd_harness.project_access import Action
from dd_sdk.contract.models import Principal
from dd_sdk.contract.problem import PROBLEM_BASE

REFUSED = "Conversion refused"
EXTENSIONS = {"application/json": "json", "application/xml": "xml"}


class ConvertRecord(RequestBody):
    """The standard to convert the approved record to, by its `conforms_to` URI."""

    refusal: ClassVar[str] = "`conforms_to` names a registered metadata standard."

    conforms_to: str


class Reduced(ResponseBody):
    """A value placed less precisely than the approved record gave it."""

    path: str
    """Its property's path in the approved record's standard."""
    reason: str


class ConvertedRecord(ResponseBody):
    """The approved metadata record in another standard, kept as a package derived from it."""

    digest: str
    """The SHA-256 of its bytes, by which it is kept and downloaded."""
    conforms_to: str
    media_type: str
    title: str
    """The target standard's name, such as Dublin Core."""
    derived_from: str
    """The digest of the approved record it was converted from."""
    unplaced: list[str]
    """The approved record's properties, by path, that the target has no place for."""
    reduced: list[Reduced]
    made_at: str


class MissingField(ResponseBody):
    """A field the target standard's set requires that the approved record gives nothing for."""

    property: str
    """Its property in the target standard."""
    label: str
    question: str
    """What to do: add it to the approved record, and approve it again."""


class ConversionRefusedProblem(common.ProblemDetails):
    """No conversion was kept, because the target requires what the approved record lacks."""

    model_config = ConfigDict(extra="forbid")

    missing: list[MissingField]


class ConvertedRecords(ResponseBody):
    """The project's converted records, newest first."""

    conversions: list[ConvertedRecord]


def _converted(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "digest": event["digest"],
        "conforms_to": event["conforms_to"],
        "media_type": event["media_type"],
        "title": event["title"],
        "derived_from": event["derived_from"],
        "unplaced": event["unplaced"],
        "reduced": event["reduced"],
        "made_at": event["at"],
    }


def routes(deps: Deps) -> list[Route]:
    conversions = "/api/projects/{project_id}/conversions"
    return [
        Route(conversions, in_project(deps, Action.CONTRIBUTE, convert), methods=["POST"]),
        Route(conversions, in_project(deps, Action.READ, list_conversions), methods=["GET"]),
        Route(
            conversions + "/{digest}",
            in_project(deps, Action.READ, get_conversion),
            methods=["GET"],
        ),
    ]


async def convert(request: Request, person: Principal, deps: Deps) -> Response:
    """Convert the approved record (`Deposit.convert_record`). Answers 201 with the conversion,
    or 409 with each field the target requires that the record cannot supply."""
    project_id = request.path_params["project_id"]
    body = await parse_body(request, ConvertRecord, REFUSED)
    if isinstance(body, Response):
        return body
    try:
        made = await run_in_threadpool(
            lambda: deps.projects.deposit.convert_record(
                project_id,
                body.conforms_to,
                acted_for=person,
                caused_by=f"POST {request.url.path}",
            )
        )
    except RepositoriesUnavailableError as exc:
        return common.problem(503, "repositories-unavailable", REFUSED, str(exc))
    except ConversionError as exc:
        return common.problem(400, "request-refused", REFUSED, str(exc))
    if not isinstance(made, Converted):
        detail = f"{made.standard} requires what the approved record does not give: " + "; ".join(
            m["label"] for m in made.missing
        )
        return respond(
            ConversionRefusedProblem,
            {
                "type": PROBLEM_BASE + "conversion-refused",
                "title": REFUSED,
                "status": 409,
                "detail": detail + ".",
                "missing": list(made.missing),
            },
            status_code=409,
            media_type="application/problem+json",
        )
    found = await run_in_threadpool(deps.projects.deposit.conversions, project_id)
    event = next(e for e in found if e["digest"] == made.digest)
    return respond(ConvertedRecord, _converted(event), status_code=201)


async def list_conversions(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(deps.projects.deposit.conversions, project_id)
    return respond(ConvertedRecords, {"conversions": [_converted(e) for e in found]})


async def get_conversion(request: Request, _: Principal, deps: Deps) -> Response:
    """A converted record's bytes, in its own media type."""
    project_id, digest = request.path_params["project_id"], request.path_params["digest"]
    found = await run_in_threadpool(deps.projects.deposit.conversions, project_id)
    event = next((e for e in found if e["digest"] == digest), None)
    content = (
        await run_in_threadpool(deps.projects.deposit.package_content, project_id, digest)
        if event
        else None
    )
    if event is None or content is None:
        return common.problem(
            404, "conversion-not-found", "No such conversion", f"Project {project_id!r} has none."
        )
    extension = EXTENSIONS.get(event["media_type"], "txt")
    name = f"metadata-record-{event['title'].lower().replace(' ', '-')}-{digest[:12]}.{extension}"
    return Response(
        content,
        media_type=event["media_type"],
        headers={"content-disposition": f'attachment; filename="{name}"'},
    )

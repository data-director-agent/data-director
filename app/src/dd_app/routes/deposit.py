"""A project's repository, its validation and deposit package, and its AI-use disclosure.

`GET /api/projects/{id}/repository` is the requirements of the repository the project chose last,
and `404` when none has been; `PUT` on it chooses one by its re3data identifier, which the pinned
re3data export resolves to the repository's name and declared standards, for the person signed in,
and answers with the requirements it resolved to and their warnings (docs/specs/deposit.md).
`GET /api/repositories?q=…` searches the pinned re3data export by name, re3data identifier,
re3data DOI or URL; without `q` it answers with the repositories the deployment suggests (its
overrides, then `suggested.yaml`), so a researcher can choose one on the project's page.
`POST /api/projects/{id}/validation` validates the project against the requirements recorded
for the repository chosen last and keeps the report; `POST /api/projects/{id}/package` does the
same and, only if the project is valid, builds the deposit package, answering `409` with the
validation when it is not; `GET /api/projects/{id}/packages/{digest}` is a package the project
log records as built, as a zip. `GET /api/projects/{id}/deposit-confirmation` is what a person
confirms before deposit and the confirmation that stands for the inventory held now, if any;
`POST` on it records that a person who may decide in the project confirmed that ethics approval,
data-protection advice and third-party rights were checked, for the inventory the project holds
now (docs/specs/deposit.md, invariant 21). `GET /api/projects/{id}/disclosure` says how each
approved document came about and what generative AI was used, as a statement and as a PROV-O
graph (docs/specs/disclosure.md).
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import ConfigDict
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app import contract_shapes as contract
from dd_app.project_service import PackageRefusedError, RepositoriesUnavailableError
from dd_app.routes.common import (
    Deps,
    Endpoint,
    Handler,
    ProblemDetails,
    RequestBody,
    ResponseBody,
    in_project,
    parse_body,
    problem,
    project_refused,
    respond,
    signed_in,
)
from dd_harness.project_access import Action
from dd_harness.projects import ProjectError
from dd_harness.requirements import RequirementsError
from dd_harness.sources import SourceConfigError
from dd_sdk.contract.models import Principal
from dd_sdk.contract.problem import PROBLEM_BASE

REPOSITORY_REFUSED = "Data Director could not record this repository"


class RepositoryMatch(ResponseBody):
    """What a search of the pinned re3data export shows of one repository."""

    re3data_id: str
    name: str
    additional_names: list[str]
    url: str | None
    doi: str | None


class RepositorySearch(ResponseBody):
    """Repositories a researcher may choose: those the pinned re3data export holds that `query`
    names, or, when `suggested`, those the deployment offers before a search."""

    snapshot_ref: str
    """The re3data export searched."""
    query: str
    suggested: bool
    repositories: list[RepositoryMatch]


class ValidationResult(ResponseBody):
    """One result of a validation: what is missing, in the harness's words."""

    message: str
    focus: str
    """The node the result is about, such as the project or the metadata record."""
    component: str
    """The check that made it."""
    path: str | None


class Validation(ResponseBody):
    """A project's validation against its chosen repository's requirements, as the harness made
    it and kept it in the project log. A violation stops the package; a warning does not, nor
    does a note, which says what was not checked or who confirmed the checks before deposit."""

    project_id: str
    conforms: bool
    validated_at: str
    report_digest: str | None
    requirements_digest: str | None
    violations: list[ValidationResult]
    warnings: list[ValidationResult]
    notes: list[ValidationResult]
    report: dict[str, Any]
    """The W3C SHACL Validation Report, in JSON-LD."""


class DepositConfirmation(ResponseBody):
    """A person's confirmation of the checks before deposit, as the project log keeps it."""

    inventory_digest: str
    """The inventory it was made for; a new inventory needs a new confirmation."""
    statements: list[str]
    """What was confirmed, in the words shown to the person."""
    confirmed_by: str
    confirmed_at: str


class DepositChecks(ResponseBody):
    """What a person confirms before deposit, in the words recorded when they do, and the
    confirmation that stands for the inventory the project holds now."""

    statements: list[str]
    confirmed: DepositConfirmation | None


class PackageLink(ResponseBody):
    """A deposit package the harness built, kept by the SHA-256 of its bytes."""

    digest: str
    size: int
    """In bytes."""
    href: str
    """Where to download it, as a zip."""


class BuiltPackage(Validation):
    """The validation that let the package be built, and the package."""

    package: PackageLink


class PackageRefusedProblem(ProblemDetails):
    """No package was built because the project is not valid: `validation` says why."""

    model_config = ConfigDict(extra="forbid")

    validation: Validation


class DisclosedModel(ResponseBody):
    """One call to a language model, as the drafting run recorded it."""

    provider: str
    model_id: str
    called_at: str
    prompt_digest: str | None


class DisclosedDraft(ResponseBody):
    """The run that drafted the text a version starts from."""

    agent_id: str
    agent_version: str
    invocation_id: str
    derivation: str
    completed_at: str | None
    models: list[DisclosedModel]


class DisclosedDocument(ResponseBody):
    """One approved version, and how it came about."""

    document_id: str
    document_kind: str
    document_title: str | None
    version: int
    digest: str
    origin: Literal["model", "model_revised", "template", "template_revised", "person"]
    draft: DisclosedDraft | None
    edited_by: list[str]
    """People who edited the text after the draft, oldest first, by name."""
    approved_by: str
    approved_at: str
    reason: str | None


class Disclosure(ResponseBody):
    """What a project's approved documents owe to generative AI: the statement, in Markdown, and
    the same account as a PROV-O graph in JSON-LD."""

    project_id: str
    made_at: str
    pending: int
    """How many documents await a decision, and so are not disclosed yet."""
    statement: str
    documents: list[DisclosedDocument]
    prov: dict[str, Any]


class ChooseRepository(RequestBody):
    """The repository, by its re3data identifier alone."""

    refusal: ClassVar[str] = "`re3data_id` is the repository's re3data identifier."

    re3data_id: str


def routes(deps: Deps) -> list[Route]:
    def read(handler: Handler) -> Endpoint:
        return in_project(deps, Action.READ, handler)

    def contribute(handler: Handler) -> Endpoint:
        return in_project(deps, Action.CONTRIBUTE, handler)

    def decide(handler: Handler) -> Endpoint:
        return in_project(deps, Action.DECIDE, handler)

    project = "/api/projects/{project_id}"
    return [
        Route(f"{project}/disclosure", read(get_disclosure), methods=["GET"]),
        Route(f"{project}/repository", read(get_repository), methods=["GET"]),
        Route(f"{project}/repository", contribute(choose_repository), methods=["PUT"]),
        Route(f"{project}/validation", contribute(validate_project), methods=["POST"]),
        Route(f"{project}/package", contribute(package_project), methods=["POST"]),
        Route(f"{project}/packages/{{digest}}", read(get_package), methods=["GET"]),
        Route(f"{project}/deposit-confirmation", read(get_checks), methods=["GET"]),
        Route(f"{project}/deposit-confirmation", decide(confirm_checks), methods=["POST"]),
        Route("/api/repositories", signed_in(deps, search_repositories), methods=["GET"]),
    ]


async def get_repository(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(deps.projects.requirements, project_id)
    if found is None:
        return problem(
            404,
            "repository-not-chosen",
            "No repository chosen",
            f"Project {project_id!r} has not chosen one.",
        )
    return respond(contract.RepositoryRequirements, found)


async def choose_repository(request: Request, person: Principal, deps: Deps) -> Response:
    """The researcher's choice of repository (`ProjectService.choose_repository`). Answers with
    the requirements it resolved to."""
    project_id = request.path_params["project_id"]
    if not deps.projects.offers_repositories:
        return _repositories_unavailable("This server has no repository requirement sets.")
    body = await parse_body(request, ChooseRepository, REPOSITORY_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        chosen = await run_in_threadpool(
            lambda: deps.projects.choose_repository(
                project_id, body.re3data_id, acted_for=person, caused_by=f"PUT {request.url.path}"
            )
        )
    except (
        RepositoriesUnavailableError,
        SourceConfigError,
        ProjectError,
        RequirementsError,
    ) as exc:
        return _choice_refused(exc, project_id)
    return respond(contract.RepositoryRequirements, chosen, status_code=201)


def _choice_refused(
    exc: RepositoriesUnavailableError | SourceConfigError | ProjectError | RequirementsError,
    project_id: str,
) -> Response:
    """The problem that answers a refused choice of repository, by what refused it, tried in the
    order the choice's handler names them."""
    if isinstance(exc, RepositoriesUnavailableError):
        return _repositories_unavailable(str(exc))
    if isinstance(exc, SourceConfigError):
        return problem(503, "re3data-unavailable", REPOSITORY_REFUSED, str(exc))
    if isinstance(exc, ProjectError):
        return project_refused(exc, project_id, REPOSITORY_REFUSED)
    return problem(400, "request-refused", REPOSITORY_REFUSED, str(exc))


def _repositories_unavailable(detail: str) -> Response:
    return problem(503, "repositories-unavailable", REPOSITORY_REFUSED, detail)


async def search_repositories(request: Request, _: Principal, deps: Deps) -> Response:
    """Repositories a researcher may choose: those the pinned re3data export holds that `q`
    names, or, without `q`, those the deployment suggests (docs/specs/deposit.md)."""
    query = request.query_params.get("q", "").strip()
    try:
        found = await run_in_threadpool(deps.projects.search_repositories, query)
    except SourceConfigError as exc:
        return problem(503, "re3data-unavailable", "Repositories cannot be searched", str(exc))
    return respond(RepositorySearch, found)


async def validate_project(request: Request, acting_for: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    validation = await run_in_threadpool(
        lambda: deps.projects.validate(
            project_id, acted_for=acting_for, caused_by=f"POST {request.url.path}"
        )
    )
    return respond(Validation, validation, status_code=201)


async def package_project(request: Request, acting_for: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    try:
        built, validation = await run_in_threadpool(
            lambda: deps.projects.package(
                project_id, acted_for=acting_for, caused_by=f"POST {request.url.path}"
            )
        )
    except PackageRefusedError as exc:
        refused = await run_in_threadpool(deps.projects.validation_view, project_id, exc.validation)
        return respond(
            PackageRefusedProblem,
            {
                "type": PROBLEM_BASE + "package-refused",
                "title": "No package was built",
                "status": 409,
                "detail": str(exc),
                "validation": refused,
            },
            status_code=409,
            media_type="application/problem+json",
        )
    return respond(
        BuiltPackage,
        {
            **validation,
            "package": {
                "digest": built.digest,
                "size": len(built.content),
                "href": f"{request.url.path.removesuffix('/package')}/packages/{built.digest}",
            },
        },
        status_code=201,
    )


async def get_checks(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(deps.projects.deposit_checks, project_id)
    return respond(DepositChecks, found)


async def confirm_checks(request: Request, person: Principal, deps: Deps) -> Response:
    """The confirmation of the checks before deposit, for the inventory the project holds now;
    `400` when it holds none."""
    project_id = request.path_params["project_id"]
    try:
        confirmed = await run_in_threadpool(
            lambda: deps.projects.confirm_deposit_checks(
                project_id, acted_for=person, caused_by=f"POST {request.url.path}"
            )
        )
    except ProjectError as exc:
        return project_refused(exc, project_id, "Data Director could not record the confirmation")
    return respond(DepositConfirmation, confirmed, status_code=201)


async def get_package(request: Request, _: Principal, deps: Deps) -> Response:
    project_id, digest = request.path_params["project_id"], request.path_params["digest"]
    content = await run_in_threadpool(deps.projects.package_content, project_id, digest)
    if content is None:
        return problem(
            404,
            "package-not-found",
            "No such package",
            f"Project {project_id!r} has built no package {digest!r}.",
        )
    return Response(
        content,
        media_type="application/zip",
        headers={
            "content-disposition": f'attachment; filename="deposit-package-{digest[:12]}.zip"'
        },
    )


async def get_disclosure(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(deps.projects.disclosure, project_id)
    return respond(Disclosure, {**found.to_document(), "prov": found.prov_jsonld()})

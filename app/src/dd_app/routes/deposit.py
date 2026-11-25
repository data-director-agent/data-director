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
validation when it is not, or while an item waits on a person's decision;
`GET /api/projects/{id}/packages/{digest}` is a package the project log records as built, as a zip.
`GET /api/projects/{id}/review` is what a person must decide and confirm before packaging;
`PUT /api/projects/{id}/review/items/{item_id}` records the signed-in person's decision on one
item, and `PUT /api/projects/{id}/review/confirmation` their confirmation of the checks before
deposit, each answering with the review as it then stands (docs/specs/deposit.md, "The pause
before packaging"). `GET /api/projects/{id}/disclosure` says how each approved document came
about and what generative AI was used, as a statement and a PROV-O graph (docs/specs/disclosure.md).
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app import contract_shapes as contract
from dd_app.deposit import DepositReviews
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
from dd_harness.deposit_review import NOTE_MAX_LENGTH, ItemDecision, UnknownItemError
from dd_harness.project_access import Action
from dd_harness.projects import ProjectError
from dd_harness.requirements import RequirementsError
from dd_harness.sources import SourceConfigError
from dd_sdk.contract.models import Principal
from dd_sdk.contract.problem import PROBLEM_BASE

REPOSITORY_REFUSED = "Data Director could not record this repository"
DECISION_REFUSED = "Data Director could not record this decision"
CONFIRMATION_REFUSED = "Data Director could not record this confirmation"


class RepositoryMatch(ResponseBody):
    """What a search of the pinned registries shows of one repository."""

    repository_id: str
    """Its re3data identifier, or, for one re3data does not list, its DataCite one."""
    registry: Literal["re3data", "datacite"]
    re3data_id: str | None
    name: str
    additional_names: list[str]
    url: str | None
    doi: str | None


class RepositorySearch(ResponseBody):
    """Repositories a researcher may choose: those the pinned re3data export, and DataCite
    snapshot, hold that `query` names, or, when `suggested`, those the deployment offers before a
    search: its institution's repositories first."""

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
    field: str | None
    """The field or document it is about, such as the repository's form label, or null."""
    supplied_on: Literal["documents", "researchers", "facts", "repository"] | None
    """The project's page where a person supplies what is missing, or null."""


class ItemDecisionMade(ResponseBody):
    """The decision a person made on an item, and who made it when."""

    decision: Literal["keep", "leave_out", "change"]
    note: str | None
    decided_by: contract.Principal
    decided_at: str


class ReviewItem(ResponseBody):
    """A file a person must decide about before packaging, and why: a name-level hint or a
    personal-data finding from the inventory."""

    item_id: str
    source: Literal["name", "finding"]
    kind: str
    path: str
    question: str
    """What the person should check, in the harness's words."""
    matched: str | None
    column: str | None
    related_paths: list[str]
    file_sha256: str | None
    decision: ItemDecisionMade | None
    """The decision that stands for this item, or null while it waits on a person."""


class ConfirmationStatement(ResponseBody):
    """One statement a person confirms before a deposit."""

    id: str
    text: str


class ChecksConfirmed(ResponseBody):
    """A person's confirmation of the checks before deposit, against the current inventory."""

    statements: list[ConfirmationStatement]
    confirmed_by: contract.Principal
    confirmed_at: str


class DepositReview(ResponseBody):
    """What a person must decide and confirm before the project is packaged. No item means that
    nothing was flagged in what was checked, never that the data are safe: `not_checked` says
    what was not."""

    inventory_digest: str | None
    items: list[ReviewItem]
    confirmation: ChecksConfirmed | None
    """The confirmation that stands for the current inventory, or null."""
    statements: list[ConfirmationStatement]
    """What the confirmation states, each of which must be confirmed."""
    not_checked: list[str]


class Validation(ResponseBody):
    """A project's validation against its chosen repository's requirements, as the harness made
    it and kept it in the project log. A violation stops the package; a warning or information
    does not; an item undecided or the checks unconfirmed hold it until a person clears them."""

    project_id: str
    conforms: bool
    ready: bool
    """Whether a package may be built: no violation, and nothing waits on a person."""
    validated_at: str
    report_digest: str | None
    requirements_digest: str | None
    violations: list[ValidationResult]
    warnings: list[ValidationResult]
    """Warnings that do not wait on a person; those that do are the `review`'s."""
    infos: list[ValidationResult]
    """Information that never blocks, such as what the repository fills in itself."""
    review: DepositReview | None
    """What a person must decide and confirm; null when no repository has been chosen."""
    report: dict[str, Any]
    """The W3C SHACL Validation Report, in JSON-LD."""


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


class DecideItem(RequestBody):
    """A person's decision on one item, with a note if they give one."""

    refusal: ClassVar[str] = (
        "`decision` is keep, leave_out or change, and `note` is text if it is given."
    )

    decision: Literal["keep", "leave_out", "change"]
    note: str | None = Field(default=None, max_length=NOTE_MAX_LENGTH)


class ConfirmChecks(RequestBody):
    """A person's confirmation of every statement, by its identifier."""

    refusal: ClassVar[str] = "`confirmed` lists the identifier of every statement confirmed."

    confirmed: list[str]


class ChooseRepository(RequestBody):
    """The repository, by its identifier alone: re3data's, or DataCite's for one re3data does
    not list."""

    refusal: ClassVar[str] = (
        "`repository_id` is the repository's re3data identifier, or its DataCite one."
    )

    repository_id: str


def routes(deps: Deps) -> list[Route]:
    def read(handler: Handler) -> Endpoint:
        return in_project(deps, Action.READ, handler)

    def contribute(handler: Handler) -> Endpoint:
        return in_project(deps, Action.CONTRIBUTE, handler)

    project = "/api/projects/{project_id}"
    return [
        Route(f"{project}/disclosure", read(get_disclosure), methods=["GET"]),
        Route(f"{project}/repository", read(get_repository), methods=["GET"]),
        Route(f"{project}/repository", contribute(choose_repository), methods=["PUT"]),
        Route(f"{project}/validation", contribute(validate_project), methods=["POST"]),
        Route(f"{project}/package", contribute(package_project), methods=["POST"]),
        Route(f"{project}/packages/{{digest}}", read(get_package), methods=["GET"]),
        Route(f"{project}/review", read(get_review), methods=["GET"]),
        Route(f"{project}/review/items/{{item_id}}", contribute(decide_item), methods=["PUT"]),
        Route(f"{project}/review/confirmation", contribute(confirm_checks), methods=["PUT"]),
        Route("/api/repositories", signed_in(deps, search_repositories), methods=["GET"]),
    ]


async def get_repository(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(deps.projects.deposit.requirements, project_id)
    if found is None:
        return problem(
            404,
            "repository-not-chosen",
            "No repository chosen",
            f"Project {project_id!r} has not chosen one.",
        )
    return respond(contract.RepositoryRequirements, found)


async def choose_repository(request: Request, person: Principal, deps: Deps) -> Response:
    """The researcher's choice of repository (`Deposit.choose_repository`). Answers with
    the requirements it resolved to."""
    project_id = request.path_params["project_id"]
    if not deps.projects.deposit.offers_repositories:
        return repositories_unavailable("This server has no repository requirement sets.")
    body = await parse_body(request, ChooseRepository, REPOSITORY_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        chosen = await run_in_threadpool(
            lambda: deps.projects.deposit.choose_repository(
                project_id,
                body.repository_id,
                acted_for=person,
                caused_by=f"PUT {request.url.path}",
            )
        )
    except (
        RepositoriesUnavailableError,
        SourceConfigError,
        ProjectError,
        RequirementsError,
    ) as exc:
        return choice_refused(exc, project_id)
    return respond(contract.RepositoryRequirements, chosen, status_code=201)


def choice_refused(
    exc: RepositoriesUnavailableError | SourceConfigError | ProjectError | RequirementsError,
    project_id: str,
) -> Response:
    """The problem that answers a refused choice of repository, by what refused it, tried in the
    order the choice's handler names them."""
    if isinstance(exc, RepositoriesUnavailableError):
        return repositories_unavailable(str(exc))
    if isinstance(exc, SourceConfigError):
        return problem(503, "re3data-unavailable", REPOSITORY_REFUSED, str(exc))
    if isinstance(exc, ProjectError):
        return project_refused(exc, project_id, REPOSITORY_REFUSED)
    return problem(400, "request-refused", REPOSITORY_REFUSED, str(exc))


def repositories_unavailable(detail: str) -> Response:
    return problem(503, "repositories-unavailable", REPOSITORY_REFUSED, detail)


async def search_repositories(request: Request, _: Principal, deps: Deps) -> Response:
    """Repositories a researcher may choose: those the pinned re3data export holds that `q`
    names, or, without `q`, those the deployment suggests (docs/specs/deposit.md)."""
    query = request.query_params.get("q", "").strip()
    try:
        found = await run_in_threadpool(deps.projects.deposit.search_repositories, query)
    except SourceConfigError as exc:
        return problem(503, "re3data-unavailable", "Repositories cannot be searched", str(exc))
    return respond(RepositorySearch, found)


async def validate_project(request: Request, acting_for: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    validation = await run_in_threadpool(
        lambda: deps.projects.deposit.validate(
            project_id, acted_for=acting_for, caused_by=f"POST {request.url.path}"
        )
    )
    return respond(Validation, validation, status_code=201)


async def package_project(request: Request, acting_for: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    try:
        built, validation = await run_in_threadpool(
            lambda: deps.projects.deposit.package(
                project_id, acted_for=acting_for, caused_by=f"POST {request.url.path}"
            )
        )
    except PackageRefusedError as exc:
        refused = await run_in_threadpool(
            deps.projects.deposit.validation_view, project_id, exc.validation
        )
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


async def get_package(request: Request, _: Principal, deps: Deps) -> Response:
    project_id, digest = request.path_params["project_id"], request.path_params["digest"]
    content = await run_in_threadpool(deps.projects.deposit.package_content, project_id, digest)
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
    found = await run_in_threadpool(deps.projects.deposit.disclosure, project_id)
    return respond(Disclosure, {**found.to_document(), "prov": found.prov_jsonld()})


async def get_review(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(DepositReviews(deps.governance).review, project_id)
    return respond(DepositReview, found)


async def decide_item(request: Request, person: Principal, deps: Deps) -> Response:
    """The signed-in person's decision on an item the deposit check lists now; `404` for an item
    it does not list."""
    project_id, item_id = request.path_params["project_id"], request.path_params["item_id"]
    body = await parse_body(request, DecideItem, DECISION_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        found = await run_in_threadpool(
            lambda: DepositReviews(deps.governance).decide(
                project_id,
                item_id,
                ItemDecision(body.decision),
                body.note,
                acted_for=person,
                caused_by=f"PUT {request.url.path}",
            )
        )
    except UnknownItemError as exc:
        return problem(404, "review-item-not-found", DECISION_REFUSED, str(exc))
    except ProjectError as exc:
        return project_refused(exc, project_id, DECISION_REFUSED)
    return respond(DepositReview, found)


async def confirm_checks(request: Request, person: Principal, deps: Deps) -> Response:
    """The signed-in person's confirmation of every statement before deposit."""
    project_id = request.path_params["project_id"]
    body = await parse_body(request, ConfirmChecks, CONFIRMATION_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        found = await run_in_threadpool(
            lambda: DepositReviews(deps.governance).confirm(
                project_id,
                body.confirmed,
                acted_for=person,
                caused_by=f"PUT {request.url.path}",
            )
        )
    except ProjectError as exc:
        return project_refused(exc, project_id, CONFIRMATION_REFUSED)
    return respond(DepositReview, found)

"""Folders on the machine the app runs on, which a local install may describe
(`dd_app.folder_scan`, docs/specs/projects.md).

`GET /api/folders` lists the folders the deployment names (`{"roots": [...]}`); with
`?root=…&path=…` it lists the subfolders of one of them, by name only, never a file.
`POST /api/folders/inventory` with `{"root": …, "path": …}` describes that folder with
`dd_inventory` and answers the inventory; it records nothing, so the inventory goes through the
researcher's check like any other before it is added to a project. Where the deployment names no
folder, both answer `404`, as they do for a folder outside the ones it names.
"""

from __future__ import annotations

from typing import ClassVar

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app import contract_shapes as contract
from dd_app.folder_scan import FolderRefusedError, FolderRoots
from dd_app.routes.common import (
    Deps,
    RequestBody,
    ResponseBody,
    parse_body,
    problem,
    respond,
    signed_in,
)
from dd_sdk.contract.models import Principal

DESCRIBE_REFUSED = "Data Director could not describe this folder"


class DescribeFolder(RequestBody):
    """Which folder to describe: a root the deployment names, and a path under it."""

    refusal: ClassVar[str] = "`root` names a listed folder and `path` a folder under it."

    root: str
    path: str = ""


class ServerFolderRoots(ResponseBody):
    """The folders on its own machine the deployment names, which a local install may describe."""

    roots: list[str]


class FolderListing(ResponseBody):
    """The subfolders of `path` under `root`, by name; never a file."""

    root: str
    path: str
    folders: list[str]


def routes(deps: Deps) -> list[Route]:
    return [
        Route("/api/folders", signed_in(deps, list_folders), methods=["GET"]),
        Route("/api/folders/inventory", signed_in(deps, describe_folder), methods=["POST"]),
    ]


def _not_found(detail: str) -> Response:
    return problem(404, "folder-not-found", "No such folder", detail)


def _no_folders() -> Response:
    return _not_found("This deployment describes no folder on its own machine.")


async def list_folders(request: Request, _: Principal, deps: Deps) -> Response:
    roots = deps.folder_roots
    if roots is None:
        return _no_folders()
    root = request.query_params.get("root")
    if root is None:
        return respond(ServerFolderRoots, {"roots": roots.names})
    path = request.query_params.get("path", "")
    try:
        folders = await run_in_threadpool(roots.subfolders, root, path)
    except FolderRefusedError as exc:
        return _not_found(str(exc))
    return respond(FolderListing, {"root": root, "path": path, "folders": folders})


async def describe_folder(request: Request, _: Principal, deps: Deps) -> Response:
    roots: FolderRoots | None = deps.folder_roots
    if roots is None:
        return _no_folders()
    body = await parse_body(request, DescribeFolder, DESCRIBE_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        inventory = await run_in_threadpool(roots.describe, body.root, body.path)
    except FolderRefusedError as exc:
        return _not_found(str(exc))
    return respond(contract.FileInventory, inventory)

"""Download a run, conversation or project as a case for debugging (docs/specs/casefile.md,
docs/guide/operations/admin.md). The harness builds the case exactly as `dd-harness case export`
does, in the service's private `/tmp`, which is removed once the response is sent; nothing in the
stores changes. Exporting is a security event, `case.exported`, which the harness records.

The service has no sign-in, so the case names the admin service as its exporter: whoever reaches
it has the VM's command line, and could run `dd-harness case export` there.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, Response

from dd_harness import casefile
from dd_sdk.contract.models import Principal, PrincipalKind

if TYPE_CHECKING:
    from dd_admin.reader import Admin

EXPORTER = Principal(
    principal_id="urn:dd:deployment:admin",
    name="Admin service",
    principal_kind=PrincipalKind.ACCOUNTABLE_ROLE,
)


def _journal(admin: Admin) -> casefile.Journal:
    """The deployment's journal, read as the service reads every journal. A journal that cannot
    be read stops the download with the reason, rather than handing over a case without it."""

    def read(since: datetime, until: datetime) -> str:
        done = admin.system.run(*casefile.journal_command(since, until))
        if done.status != 0:
            raise HTTPException(502, (done.err or done.out or "journalctl failed").strip())
        return done.out

    return read


def options(admin: Admin, request: Request) -> casefile.Options:
    """How the case is written, from the download form: content named or carried, and the
    journal only where the service reads journals (`DD_ADMIN_SYSTEMD`)."""
    query = request.query_params
    journal = admin.settings.systemd and query.get("journal") == "1"
    return casefile.Options(
        content="named" if query.get("content") == "named" else "carried",
        journal=_journal(admin) if journal else None,
    )


def download(admin: Admin, request: Request) -> Response:
    """The case of `{scope}/{ident}` as a zip; 404 for a scope or identifier the stores do not
    hold."""
    scope, ident = request.path_params["scope"], request.path_params["ident"]
    if scope not in casefile.SCOPES:
        raise HTTPException(404, f"a case is of a {', '.join(casefile.SCOPES)}")
    if admin.runs is None:
        raise HTTPException(404, "no run store is configured")
    scratch = Path(tempfile.mkdtemp(prefix="dd-case-"))
    target = scratch / "case.zip"
    try:
        digest = casefile.export(
            target,
            admin.runs,
            casefile.project_log(admin.projects),
            scope,
            ident,
            EXPORTER,
            options(admin, request),
        )
    except BaseException as exc:
        shutil.rmtree(scratch, ignore_errors=True)
        if isinstance(exc, LookupError):
            raise HTTPException(404, f"no {scope} with that identifier") from None
        raise
    return FileResponse(
        target,
        media_type="application/zip",
        filename=f"case-{scope}-{ident}.zip",
        headers={"x-case-digest": f"sha256:{digest}"},
        background=BackgroundTask(shutil.rmtree, scratch, ignore_errors=True),
    )

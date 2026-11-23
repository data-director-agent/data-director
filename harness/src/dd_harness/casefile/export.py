"""Export a case: select, copy, index, then name every file's digest in `case.json`
(docs/specs/casefile.md). Exporting reads records, so it is a security event, `case.exported`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from dd_harness.casefile.copy import copy_project, copy_runs
from dd_harness.casefile.index import write_index, write_timeline
from dd_harness.casefile.select import Selection, select
from dd_harness.package_crate import ZIP_TIME
from dd_harness.project_log import ProjectLog
from dd_harness.storage import RunStorage
from dd_sdk.contract.models import Principal
from dd_sdk.security_log import SecurityEvent, emit

FORMAT = "dd-case-1"
MANIFEST = "case.json"


def _harness_version() -> str:
    try:
        return version("data-director-harness")
    except PackageNotFoundError:
        return "unknown"


def file_digests(root: Path) -> dict[str, str]:
    """The SHA-256 of every file in the case but the manifest, by its path from the case root."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.relative_to(root).as_posix() != MANIFEST
    }


def _manifest(selection: Selection, exported_by: Principal) -> dict[str, Any]:
    runs = selection.runs
    return {
        "format": FORMAT,
        "scope": selection.scope,
        "id": selection.ident,
        "project_id": selection.project_id,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "exported_by": exported_by.principal_id,
        "harness_version": _harness_version(),
        "contracts": sorted({str(e.get("contract_version")) for e in runs}),
        "policy_digests": sorted({str(e.get("policy_digest")) for e in runs}),
        "agents": sorted({f"{e.get('agent_id')} {e.get('agent_version')}" for e in runs}),
        "runs": [e["invocation_id"] for e in runs],
    }


def write_zip(root: Path, target: Path) -> None:
    """The case directory as a zip whose bytes depend on its content alone."""
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(path.relative_to(root).as_posix(), date_time=ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())


def _record(selection: Selection, exported_by: Principal) -> None:
    context: dict[str, str] = {}
    if selection.scope == "run":
        context["invocation_id"] = selection.ident
    elif selection.scope == "conversation":
        context["conversation_id"] = selection.ident
    if selection.project_id is not None:
        context["project_id"] = selection.project_id
    emit(
        SecurityEvent.CASE_EXPORTED,
        outcome="success",
        service="harness",
        principal=exported_by.principal_id,
        action=selection.scope,
        **context,
    )


def build(
    root: Path,
    runs: RunStorage,
    log: ProjectLog | None,
    scope: str,
    ident: str,
    exported_by: Principal,
) -> Mapping[str, Any]:
    """Write the case of `scope` and `ident` into the empty directory `root`, and return its
    manifest. `LookupError` if the stores hold no such run, conversation or project."""
    selection = select(runs, log, scope, ident)
    copy_runs(runs, selection.runs, root)
    if selection.project_id is not None and log is not None and log.exists(selection.project_id):
        copy_project(log, selection.project_id, root)
    manifest = _manifest(selection, exported_by)
    write_timeline(root, selection)
    write_index(root, selection, manifest)
    manifest = {**manifest, "files": file_digests(root)}
    (root / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _record(selection, exported_by)
    return manifest


def export(
    target: Path,
    runs: RunStorage,
    log: ProjectLog | None,
    scope: str,
    ident: str,
    exported_by: Principal,
) -> str:
    """Export the case to `target`, a new directory or, if it ends `.zip`, a zip file, and return
    the SHA-256 of its `case.json`, which names every other file's."""
    if target.exists():
        raise FileExistsError(f"{target} exists; a case is written only to a new path")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix != ".zip":
        target.mkdir(parents=True)
        try:
            build(target, runs, log, scope, ident, exported_by)
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return hashlib.sha256((target / MANIFEST).read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch) / "case"
        root.mkdir()
        try:
            build(root, runs, log, scope, ident, exported_by)
            write_zip(root, target)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return hashlib.sha256((root / MANIFEST).read_bytes()).hexdigest()

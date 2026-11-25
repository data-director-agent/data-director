"""Export a case: select, copy, add the journal lines, index, then name every file's digest in
`case.json` (docs/specs/casefile.md). Exporting reads records, so it is a security event,
`case.exported`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from dd_harness.casefile.copy import copy_project, copy_runs
from dd_harness.casefile.index import timeline, write_index, write_timeline
from dd_harness.casefile.journal import JOURNAL, Journal, journal_lines, span
from dd_harness.casefile.naming import Content, shaper
from dd_harness.casefile.select import Selection, select
from dd_harness.package_crate import ZIP_TIME
from dd_harness.project_log import ProjectLog
from dd_harness.storage import RunStorage
from dd_sdk.contract.models import Principal
from dd_sdk.security_log import SecurityEvent, emit

FORMAT = "dd-case-1"
MANIFEST = "case.json"


@dataclass(frozen=True)
class Options:
    """How a case is written: its content carried or named by digest
    (`dd_harness.casefile.naming`), and the journal to keep the lines that name it from, if any."""

    content: Content = "carried"
    journal: Journal | None = None


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


def _manifest(selection: Selection, exported_by: Principal, content: Content) -> dict[str, Any]:
    runs = selection.runs
    return {
        "format": FORMAT,
        "content": content,
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
                archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)


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


def _identifiers(selection: Selection) -> Iterator[str]:
    """Every identifier a journal line about the case could name."""
    yield selection.ident
    if selection.project_id is not None:
        yield selection.project_id
    for envelope in selection.runs:
        yield envelope["invocation_id"]
        yield str(envelope.get("conversation_id") or "")
        yield str((envelope.get("telemetry") or {}).get("trace_id") or "")


def _write_journal(root: Path, selection: Selection, journal: Journal, content: Content) -> None:
    """`journal.jsonl`: the journal lines in the case's time span that name it."""
    found = span(line["at"] for line in timeline(root, selection))
    if found is None:
        return
    shape = shaper(content)
    lines = journal_lines(journal(*found), _identifiers(selection))
    text = "".join(json.dumps(shape(line), sort_keys=True) + "\n" for line in lines)
    (root / JOURNAL).write_text(text, encoding="utf-8")


def build(
    root: Path,
    runs: RunStorage,
    log: ProjectLog | None,
    scope: str,
    ident: str,
    exported_by: Principal,
    options: Options | None = None,
) -> Mapping[str, Any]:
    """Write the case of `scope` and `ident` into the empty directory `root`, as `options` say,
    and return its manifest. `LookupError` if the stores hold no such run, conversation or
    project."""
    options = options or Options()
    content, journal = options.content, options.journal
    found = select(runs, log, scope, ident)
    copy_runs(runs, found.runs, root, content)
    if found.project_id is not None and log is not None and log.exists(found.project_id):
        copy_project(log, found.project_id, root, content)
    if journal is not None:
        _write_journal(root, found, journal, content)
    # What is derived from the runs is derived from them as the case holds them.
    selection = replace(found, runs=tuple(shaper(content)(e) for e in found.runs))
    manifest = _manifest(selection, exported_by, content)
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
    options: Options | None = None,
) -> str:
    """Export the case to `target`, a new directory or, if it ends `.zip`, a zip file, as
    `options` say, and return the SHA-256 of its `case.json`, which names every other file's."""
    if target.exists():
        raise FileExistsError(f"{target} exists; a case is written only to a new path")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix != ".zip":
        target.mkdir(parents=True)
        try:
            build(target, runs, log, scope, ident, exported_by, options)
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return hashlib.sha256((target / MANIFEST).read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch) / "case"
        root.mkdir()
        try:
            build(root, runs, log, scope, ident, exported_by, options)
            write_zip(root, target)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return hashlib.sha256((root / MANIFEST).read_bytes()).hexdigest()

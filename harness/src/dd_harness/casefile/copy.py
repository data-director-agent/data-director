"""A case's records: the selected runs and project, copied from any backend into the file layout,
so `runs/` is a `DD_RUNS_DIR` and `projects/` a `DD_PROJECTS_DIR` every reader opens
(docs/specs/casefile.md, Layout). Everything is written through the file backends, never by hand.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from dd_harness.package_crate import CRATE_FILES
from dd_harness.project_files import FileProjectLog
from dd_harness.project_log import ProjectLog
from dd_harness.storage import (
    CRATE,
    GROUNDING,
    SOURCES,
    SPANS,
    STAGES,
    VALIDATION,
    WITHHELD,
    RunStorage,
)
from dd_harness.store import RunStore
from dd_sdk.contract.classes import ClassSchema

RUNS = "runs"
PROJECTS = "projects"

# Every artifact the conductor keeps (dd_harness.pipeline.store_run); whichever a run has is copied.
ARTIFACTS = (
    SPANS,
    GROUNDING,
    SOURCES,
    VALIDATION,
    STAGES,
    WITHHELD,
    *(f"{CRATE}/{name}" for name in CRATE_FILES),
)
_DIGEST = re.compile(r"[0-9a-f]{64}")


def _schemas(source: RunStorage, envelope: Mapping[str, Any]) -> list[ClassSchema]:
    """The class schemas the run was checked against, by the digests its envelope names."""
    found = []
    for key in ("input_schema", "payload_schema"):
        digest = envelope.get(key)
        if digest and (schema := source.get_schema(digest)) is not None:
            found.append(ClassSchema(name=key, json_schema=schema, digest=digest))
    return found


def copy_runs(source: RunStorage, envelopes: tuple[Mapping[str, Any], ...], out: Path) -> None:
    """Each run as stored, with its request, prompts, class schemas and artifacts, in order."""
    target = RunStore(out / RUNS)
    for selected in envelopes:
        invocation_id = selected["invocation_id"]
        envelope = source.get(invocation_id) or dict(selected)
        target.append(
            envelope,
            source.get_request(invocation_id),
            _schemas(source, envelope),
            source.get_prompts(invocation_id),
        )
        artifacts = {
            name: data
            for name in ARTIFACTS
            if (data := source.get_artifact(invocation_id, name)) is not None
        }
        if artifacts:
            target.put_artifacts(invocation_id, artifacts)


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _strings(item)


def copy_project(source: ProjectLog, project_id: str, out: Path) -> None:
    """The project's log, every event in order, and every blob an event names. A blob is found by
    any digest in the log that the project keeps content under, so an event type added later needs
    no change here."""
    events = source.events(project_id)
    target = FileProjectLog(out / PROJECTS)
    target.create(project_id, events[0])
    if events[1:]:
        with target.section(project_id) as section:
            section.append(events[1:])
    digests = {s for event in events for s in _strings(event) if _DIGEST.fullmatch(s)}
    for digest in sorted(digests):
        if (content := source.blob(project_id, digest)) is not None:
            target.keep_blob(project_id, digest, content)

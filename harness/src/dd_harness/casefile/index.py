"""What a person or a coding agent reads first in a case: `timeline.jsonl`, everything recorded,
merged by time, and `CASE.md`, an index with the failures first (docs/specs/casefile.md, Index).
Both are derived from the case's records and never authoritative.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dd_harness.casefile.copy import PROJECTS, RUNS
from dd_harness.casefile.journal import JOURNAL
from dd_harness.casefile.select import Selection
from dd_harness.storage import GROUNDING, SOURCES, SPANS, STAGES, WITHHELD

TIMELINE = "timeline.jsonl"
INDEX = "CASE.md"
# What to open for a run that did not succeed, in the order to read it.
TO_OPEN = ("envelope.json", STAGES, SPANS, GROUNDING, SOURCES, WITHHELD)


def _at(value: str) -> str:
    """A time as UTC ISO 8601 with milliseconds, so lines from every source sort together."""
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _run_lines(root: Path, envelope: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    invocation_id = envelope["invocation_id"]
    where = f"{RUNS}/{invocation_id}"
    for record in _jsonl(root / where / STAGES):
        detail = {k: v for k, v in record.items() if k not in ("at", "event")}
        yield {
            "at": _at(record["at"]),
            "kind": "stage",
            "what": record["event"],
            "run": invocation_id,
            "detail": detail,
            "file": f"{where}/{STAGES}",
        }
    outcome = envelope.get("outcome") or {}
    yield {
        "at": _at(envelope["completed_at"]),
        "kind": "run",
        "what": "completed",
        "run": invocation_id,
        "detail": {
            "agent_id": envelope.get("agent_id"),
            "status": outcome.get("status"),
            "reason_code": outcome.get("reason_code"),
            "problem": (envelope.get("problem") or {}).get("type"),
            "parent": envelope.get("parent_invocation_id"),
            "conversation": envelope.get("conversation_id"),
        },
        "file": f"{where}/envelope.json",
    }


def _journal_lines(root: Path) -> Iterator[dict[str, Any]]:
    for line in _jsonl(root / JOURNAL):
        detail = {k: v for k, v in line.items() if k not in ("at", "unit")}
        yield {
            "at": _at(line["at"]),
            "kind": "journal",
            "what": line.get("unit"),
            "detail": detail,
            "file": JOURNAL,
        }


def timeline(root: Path, selection: Selection) -> list[dict[str, Any]]:
    """Every project event, stage record, run completion and journal line in the case, by
    time."""
    lines: list[dict[str, Any]] = []
    if selection.project_id is not None:
        where = f"{PROJECTS}/{selection.project_id}/events.jsonl"
        for event in _jsonl(root / where):
            detail = {k: v for k, v in event.items() if k not in ("at", "event")}
            lines.append(
                {
                    "at": _at(event["at"]),
                    "kind": "project",
                    "what": event["event"],
                    "detail": detail,
                    "file": where,
                }
            )
    for envelope in selection.runs:
        lines.extend(_run_lines(root, envelope))
    lines.extend(_journal_lines(root))
    return sorted(lines, key=lambda line: line["at"])


def write_timeline(root: Path, selection: Selection) -> None:
    text = "".join(json.dumps(line, sort_keys=True) + "\n" for line in timeline(root, selection))
    (root / TIMELINE).write_text(text, encoding="utf-8")


def _status(envelope: Mapping[str, Any]) -> str:
    return str((envelope.get("outcome") or {}).get("status", "unknown"))


def _failure(root: Path, envelope: Mapping[str, Any]) -> list[str]:
    invocation_id = envelope["invocation_id"]
    outcome = envelope.get("outcome") or {}
    problem = envelope.get("problem") or {}
    where = root / RUNS / invocation_id
    to_open = [f"`{RUNS}/{invocation_id}/{name}`" for name in TO_OPEN if (where / name).exists()]
    return [
        f"### {envelope.get('agent_id')} — {_status(envelope)} (`{invocation_id}`)",
        "",
        f"- Completed: {envelope.get('completed_at')}",
        f"- Reason code: {outcome.get('reason_code') or 'none'}",
        f"- Problem: {problem.get('type') or 'none'}",
        f"- Statement: {outcome.get('statement') or ''}".rstrip(),
        f"- Delegated by: `{envelope['parent_invocation_id']}`"
        if envelope.get("parent_invocation_id")
        else "- Delegated by: none (a turn)",
        f"- Open: {', '.join(to_open)}",
        "",
    ]


def _run_row(envelope: Mapping[str, Any]) -> str:
    depth = "↳ " if envelope.get("parent_invocation_id") else ""
    reason = (envelope.get("outcome") or {}).get("reason_code") or ""
    return (
        f"| {envelope.get('completed_at')} | {depth}{envelope.get('agent_id')} "
        f"| {_status(envelope)} | {reason} | `{envelope['invocation_id']}` |"
    )


def _named(manifest: Mapping[str, Any]) -> list[str]:
    if manifest.get("content") != "named":
        return []
    return [
        "",
        "Content is named, not carried: every text is the `ni:` digest of its UTF-8 bytes, and the",
        "project's files are left out. Identifiers, times, statuses, codes and titles are kept.",
    ]


def write_index(root: Path, selection: Selection, manifest: Mapping[str, Any]) -> None:
    """`CASE.md`: the case's scope and build, each run that did not succeed and what to open
    for it, then every run in order."""
    failed = [e for e in selection.runs if _status(e) != "succeeded"]
    lines = [
        f"# Case: {selection.scope} `{selection.ident}`",
        "",
        f"- Format: {manifest['format']}; exported {manifest['created_at']}"
        f" by {manifest['exported_by']}",
        f"- Harness {manifest['harness_version']}, contract {', '.join(manifest['contracts'])}",
        f"- Project: `{selection.project_id}`" if selection.project_id else "- Project: none",
        f"- Runs: {len(selection.runs)}, of which {len(failed)} did not succeed",
        "",
        "Check the case before reading it: `dd-harness case verify <this directory or zip>`.",
        f"Open it with any reader: `DD_RUNS_DIR={RUNS} DD_PROJECTS_DIR={PROJECTS}`.",
        f"Everything in time order is in `{TIMELINE}`"
        + (
            f", with the service journal's lines from `{JOURNAL}`."
            if (root / JOURNAL).exists()
            else "."
        ),
        *_named(manifest),
        "",
        "## Runs that did not succeed",
        "",
    ]
    for envelope in failed:
        lines += _failure(root, envelope)
    if not failed:
        lines += ["None.", ""]
    lines += [
        "## Every run",
        "",
        "| Completed | Agent | Status | Reason | Run |",
        "|---|---|---|---|---|",
        *(_run_row(e) for e in selection.runs),
        "",
    ]
    (root / INDEX).write_text("\n".join(lines), encoding="utf-8")

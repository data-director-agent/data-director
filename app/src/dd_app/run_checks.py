"""What the grounding linter and the source check reported on a stored run."""

from __future__ import annotations

from typing import Any

from dd_harness.storage import GROUNDING, SOURCES, RunStorage


def _report(stored: bytes | None) -> dict[str, Any] | None:
    """A check's stored summary (`GroundingReport.summary`, `SourceReport.summary`), which says
    `FAILED` when the check failed."""
    if stored is None:
        return None
    summary = stored.decode("utf-8").strip()
    return {"passed": "FAILED" not in summary, "summary": summary}


def stored_checks(store: RunStorage, invocation_id: str) -> dict[str, Any]:
    """The reports from the summaries the conductor stores beside the run. The conductor runs both
    checks over every envelope it stores, even one the gate refused; a report the run does not
    have is None."""
    return {
        "grounding": _report(store.get_artifact(invocation_id, GROUNDING)),
        "sources": _report(store.get_artifact(invocation_id, SOURCES)),
    }

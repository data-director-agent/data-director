"""A project's validation and deposit package as the shell draws them (docs/specs/deposit.md).

The harness validates and builds (`dd_harness.deposit`). The app passes on what it found,
unchanged except for its shape: each violation and warning with the message the harness wrote,
the SHACL Validation Report itself, and the digest each is kept by in the project log.
"""

from __future__ import annotations

import re
from typing import Any

from dd_harness.deposit import Result, Validation
from dd_harness.projects import PROJECT_VALIDATED
from dd_harness.storage import ProjectStorage

DIGEST = re.compile(r"[0-9a-f]{64}")


def _result(result: Result) -> dict[str, Any]:
    return {
        "message": result.message,
        "focus": result.focus,
        "component": result.component,
        "path": result.path,
    }


def validation_view(validation: Validation, report_digest: str | None) -> dict[str, Any]:
    """`validation` as the shell draws it; `report_digest` is what the project log keeps the
    report by."""
    return {
        "project_id": validation.project_id,
        "conforms": validation.conforms,
        "validated_at": validation.made_at.isoformat(),
        "report_digest": report_digest,
        "requirements_digest": validation.requirements_digest,
        "violations": [_result(r) for r in validation.violations],
        "warnings": [_result(r) for r in validation.warnings],
        "report": validation.report_jsonld(),
    }


def last_report_digest(projects: ProjectStorage, project_id: str) -> str | None:
    """The digest of the validation report the project log kept last, or None."""
    found = [e for e in projects.events(project_id) if e["event"] == PROJECT_VALIDATED]
    return found[-1]["digest"] if found else None

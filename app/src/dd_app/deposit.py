"""A project's validation and deposit package as the shell draws them (docs/specs/deposit.md, #623).

The harness validates, keeps the report and builds the package (`dd_harness.deposit`). The app
calls it in-process, as it calls `disclose`, and passes on what it says: whether the project
conforms, each violation and warning with the message the harness wrote, and the SHACL report
itself. It holds no rule of its own about what makes a project valid.
"""

from __future__ import annotations

import re
from typing import Any

from dd_harness.deposit import Package, Result, Validation

DIGEST = re.compile(r"[0-9a-f]{64}")
PACKAGE_MEDIA_TYPE = "application/zip"


def _result(result: Result) -> dict[str, Any]:
    return {
        "severity": result.severity,
        "message": result.message,
        "focus": result.focus,
        "component": result.component,
        "path": result.path,
    }


def validation_view(validation: Validation, report_digest: str | None = None) -> dict[str, Any]:
    """`POST /api/projects/{id}/validations`, and the validation behind a package or a refusal:
    whether the project conforms, its violations then its warnings, and the SHACL report."""
    view: dict[str, Any] = {
        "project_id": validation.project_id,
        "made_at": validation.made_at.isoformat(),
        "conforms": validation.conforms,
        "requirements_digest": validation.requirements_digest,
        "violations": [_result(r) for r in validation.violations],
        "warnings": [_result(r) for r in validation.warnings],
        "report": validation.report_jsonld(),
    }
    if report_digest is not None:
        view["report_digest"] = report_digest
    return view


def package_view(package: Package) -> dict[str, Any]:
    """`POST /api/projects/{id}/packages`: the package's digest and size, which name it for
    download, and the validation it was built from."""
    return {
        "digest": package.digest,
        "size": len(package.content),
        "media_type": PACKAGE_MEDIA_TYPE,
        "validation": validation_view(package.validation),
    }


def package_filename(project_id: str, digest: str) -> str:
    """What a downloaded package is called: the project and the start of its digest."""
    return f"deposit-{project_id}-{digest[:12]}.zip"

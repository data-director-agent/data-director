"""A project's validation and deposit package as the shell draws them, and what a person decides
before packaging (docs/specs/deposit.md).

The harness validates, builds and keeps each decision (`dd_harness.deposit`,
`dd_harness.deposit_review`). The app passes on what it found, unchanged except for its shape:
each violation and warning with the message the harness wrote, the SHACL Validation Report
itself, the digest each is kept by in the project log, and the items a person must decide, with
the decision that stands for each. What waits on a person is drawn from the review, so it is
left out of the warnings rather than shown twice.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from dd_app.governance import Governance
from dd_harness import deposit_review
from dd_harness.deposit import Result, Validation
from dd_harness.deposit_review import REVIEW_CHECKS, ItemDecision
from dd_harness.projects import PROJECT_VALIDATED, UnknownProjectError
from dd_harness.storage import DepositSource, ProjectRecord
from dd_sdk.contract.models import Principal

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
        "ready": validation.ready,
        "validated_at": validation.made_at.isoformat(),
        "report_digest": report_digest,
        "requirements_digest": validation.requirements_digest,
        "violations": [_result(r) for r in validation.violations],
        "warnings": [_result(r) for r in validation.warnings if r.component not in REVIEW_CHECKS],
        "review": validation.review.to_document() if validation.review else None,
        "report": validation.report_jsonld(),
    }


def last_report_digest(projects: ProjectRecord, project_id: str) -> str | None:
    """The digest of the validation report the project log kept last, or None."""
    found = [e for e in projects.events(project_id) if e["event"] == PROJECT_VALIDATED]
    return found[-1]["digest"] if found else None


@dataclass(frozen=True)
class DepositReviews:
    """What the app's routes may do about the pause before packaging: read it, and record the
    signed-in person's decision on an item or their confirmation of the checks. Every method
    blocks, so a route calls it off the event loop."""

    governance: Governance

    @property
    def _store(self) -> DepositSource:
        if self.governance.projects is None:
            raise UnknownProjectError("this server keeps no projects")
        return self.governance.projects

    def review(self, project_id: str) -> dict[str, Any]:
        return deposit_review.review(self._store, project_id).to_document()

    def decide(
        self,
        project_id: str,
        item_id: str,
        decision: ItemDecision,
        note: str | None,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any]:
        """Record the decision and answer with the review as it now stands."""
        deposit_review.decide_item(
            self._store,
            project_id,
            item_id,
            decision,
            note,
            acted_for=acted_for,
            caused_by=caused_by,
        )
        return self.review(project_id)

    def confirm(
        self, project_id: str, confirmed: Collection[str], *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Record the confirmation and answer with the review as it now stands."""
        deposit_review.confirm(
            self._store, project_id, confirmed, acted_for=acted_for, caused_by=caused_by
        )
        return self.review(project_id)

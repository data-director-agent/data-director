"""What validating a project for deposit gives: the `Validation`, the `Package` built from a valid
one, and the error that refuses a package (docs/specs/deposit.md). `dd_harness.deposit` makes
them; they are kept apart so that it stays within its size.

A validation is ready to package when its report has no violation (it conforms, in SHACL's sense)
and nothing waits on a person (`dd_harness.deposit_review`): no item is undecided and the checks
before deposit are confirmed. Both are carried in the report as warnings, which in SHACL do not
make it fail to conform; the package is refused until they are cleared all the same. Information
(`sh:Info`), such as what the repository fills in itself, never blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dd_harness.deposit_review import REVIEW_CHECKS, Review
from dd_harness.disclosure import ni
from dd_harness.projects import ProjectError
from dd_harness.shacl import INFO, VIOLATION, WARNING, Result
from dd_harness.shacl import report_jsonld as shacl_report


class PackageRefusedError(ProjectError):
    """The project is not valid against its repository's requirements, or waits on a person's
    decision, so no package is built. The validation, with every reason, is in `validation`; it
    is kept in the project log."""

    def __init__(self, validation: Validation) -> None:
        reasons = "; ".join(r.message for r in validation.violations + validation.awaiting)
        super().__init__(f"the project is not ready for deposit: {reasons}")
        self.validation = validation


@dataclass(frozen=True)
class Validation:
    """The validation of a project against the merged requirement set recorded for it, and what
    a person must decide before it is packaged."""

    project_id: str
    made_at: datetime
    # The digest of the merged requirement set checked against, or None if none was chosen.
    requirements_digest: str | None
    results: tuple[Result, ...]
    # What a person must decide and confirm, or None when no repository is chosen.
    review: Review | None = None

    @property
    def conforms(self) -> bool:
        return not self.violations

    @property
    def ready(self) -> bool:
        """Whether a package may be built: no violation, and nothing waits on a person."""
        return self.conforms and self.review is not None and not self.review.paused

    @property
    def violations(self) -> tuple[Result, ...]:
        return tuple(r for r in self.results if r.severity == VIOLATION)

    @property
    def warnings(self) -> tuple[Result, ...]:
        return tuple(r for r in self.results if r.severity == WARNING)

    @property
    def infos(self) -> tuple[Result, ...]:
        """What the validation says for information only, such as what the repository fills in
        itself; it never blocks."""
        return tuple(r for r in self.results if r.severity == INFO)

    @property
    def awaiting(self) -> tuple[Result, ...]:
        """The warnings that wait on a person's decision or confirmation."""
        return tuple(r for r in self.warnings if r.component in REVIEW_CHECKS)

    def report_jsonld(self) -> dict[str, Any]:
        """The SHACL Validation Report, in JSON-LD."""
        about: dict[str, Any] = {
            "dd:project": {"@id": project_iri(self.project_id)},
            "dd:validated_at": {"@value": self.made_at.isoformat(), "@type": "xsd:dateTime"},
            "dd:ready_to_package": self.ready,
        }
        if self.requirements_digest is not None:
            about["dd:requirements"] = {"@id": ni(self.requirements_digest)}
        if self.review is not None:
            about["dd:not_checked"] = list(self.review.not_checked)
        return shacl_report(self.results, **about)


@dataclass(frozen=True)
class Package:
    """A deposit package, as the project log keeps it."""

    digest: str
    content: bytes
    validation: Validation


def project_iri(project_id: str) -> str:
    return f"urn:uuid:{project_id}"

"""What a project keeps of getting its data deposited: each validation of it against its
repository's requirements, each decision and confirmation a person makes before packaging, each
deposit package built, and each deposit a person approved with its outcome (docs/specs/deposit.md,
invariants 8, 9, 12, 15 and 20 to 22)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from dd_harness.projects.rules import (
    DEPOSIT_APPROVED,
    DEPOSIT_CHECKS_CONFIRMED,
    DEPOSIT_FAILED,
    DEPOSIT_ITEM_DECIDED,
    DEPOSIT_RECORDED,
    ENVELOPE_KEYS,
    PACKAGE_BUILT,
    PROJECT_VALIDATED,
    ProjectError,
    ProjectRules,
)
from dd_sdk.contract.models import Principal
from dd_sdk.evidence import INPUT_CANONICALISATION, canonicalise, input_hash

# The format of a package whose `package_built` event names none: every package built before
# packages named their format was the RO-Crate zip (docs/specs/deposit.md, invariant 19).
RO_CRATE = "ro-crate"
OUTCOMES = frozenset({DEPOSIT_RECORDED, DEPOSIT_FAILED})


def package_format(event: Mapping[str, Any]) -> str:
    """The format a `package_built` event names."""
    return str(event.get("format") or RO_CRATE)


class DepositInProgressError(ProjectError):
    """The package was already approved for the repository, and that deposit has no outcome yet,
    or has made a draft: a second approval is refused (docs/specs/deposit.md, invariant 15)."""

    def __init__(self, message: str, earlier: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.earlier = dict(earlier)


class DepositRecords(ProjectRules):
    """The rules of the validation reports and deposit packages a project keeps."""

    def record_validation(
        self,
        project_id: str,
        report: Mapping[str, Any],
        *,
        conforms: bool,
        requirements_digest: str | None,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Keep a SHACL Validation Report of the project against its requirements
        (docs/specs/deposit.md, invariant 8), and its `project_validated` event. Returns the
        report's digest. Raises `ProjectError` for an unknown project."""
        self._require(project_id)
        document = dict(report)
        digest = input_hash(document)
        self._keep_blob(project_id, digest, canonicalise(document, INPUT_CANONICALISATION))
        self._append(
            project_id,
            PROJECT_VALIDATED,
            acted_for,
            caused_by,
            {
                "digest": digest,
                "canonicalisation": INPUT_CANONICALISATION,
                "conforms": conforms,
                "requirements_digest": requirements_digest,
            },
        )
        return digest

    def record_item_decision(
        self,
        project_id: str,
        decision: Mapping[str, Any],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> None:
        """Keep a person's decision on an item the deposit check asked them to decide, as a
        `deposit_item_decided` event carrying `decision` (`dd_harness.deposit_review`,
        docs/specs/deposit.md, invariant 21). Raises `ProjectError` for an unknown project."""
        detail = {key: value for key, value in decision.items() if key not in ENVELOPE_KEYS}
        self._append(project_id, DEPOSIT_ITEM_DECIDED, acted_for, caused_by, detail)

    def record_confirmation(
        self,
        project_id: str,
        confirmation: Mapping[str, Any],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> None:
        """Keep a person's confirmation that the checks before deposit were made, as a
        `deposit_checks_confirmed` event carrying `confirmation` (`dd_harness.deposit_review`,
        docs/specs/deposit.md, invariant 22). Raises `ProjectError` for an unknown project."""
        detail = {key: value for key, value in confirmation.items() if key not in ENVELOPE_KEYS}
        self._append(project_id, DEPOSIT_CHECKS_CONFIRMED, acted_for, caused_by, detail)

    def record_package(
        self,
        project_id: str,
        package: bytes,
        *,
        about: Mapping[str, Any],
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Keep a deposit package by the SHA-256 of its bytes, and its `package_built` event,
        which carries `about` (docs/specs/deposit.md, invariant 9). Returns the digest. Raises
        `ProjectError` for an unknown project."""
        self._require(project_id)
        digest = hashlib.sha256(package).hexdigest()
        self._keep_blob(project_id, digest, package)
        detail = {key: value for key, value in about.items() if key not in ENVELOPE_KEYS}
        # The RO-Crate package unless `about` names another format (invariant 19).
        detail = {"format": RO_CRATE, **detail, "digest": digest}
        self._append(project_id, PACKAGE_BUILT, acted_for, caused_by, detail)
        return digest

    def package(self, project_id: str, digest: str) -> bytes | None:
        """The bytes of a package the project log records as built, or None if it records no
        package with this digest. Raises `ProjectError` for an unknown project."""
        built = any(
            e["event"] == PACKAGE_BUILT and e["digest"] == digest for e in self.events(project_id)
        )
        if not built:
            return None
        return self._blob(project_id, digest)

    def approve_deposit(
        self,
        project_id: str,
        approval: Mapping[str, Any],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any]:
        """Record a person's approval to deposit a package in a repository, as a
        `deposit_approved` event carrying `approval`, which names at least the package's
        `digest` and the repository's `repository_id`. Returns the event.

        In the project's exclusive section, so two approvals of one package cannot both pass:
        raises `DepositInProgressError` if the log already records an approval of the package
        for the repository that ended in a draft or has no outcome yet. An approval that ended
        in `deposit_failed` does not count, so trying again needs only a new approval. Raises
        `ProjectError` for an unknown or deleted project."""
        detail = {key: value for key, value in approval.items() if key not in ENVELOPE_KEYS}
        with self._section(project_id) as section:
            events = section.events()
            ended = {e["approval"]: e for e in events if e["event"] in OUTCOMES}
            for earlier in events:
                if (
                    earlier["event"] != DEPOSIT_APPROVED
                    or earlier["digest"] != detail["digest"]
                    or _repository(earlier) != _repository(detail)
                ):
                    continue
                outcome = ended.get(earlier["event_id"])
                if outcome is None:
                    raise DepositInProgressError(
                        "this package is already being deposited in the repository", earlier
                    )
                if outcome["event"] == DEPOSIT_RECORDED:
                    raise DepositInProgressError(
                        "this package was already deposited in the repository", outcome
                    )
            event = self._event(project_id, DEPOSIT_APPROVED, acted_for, caused_by, detail)
            section.append([event])
        return event

    def record_deposit_outcome(
        self,
        project_id: str,
        outcome: Mapping[str, Any],
        *,
        recorded: bool,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any]:
        """Record how an approved deposit ended: `deposit_recorded` when the repository made the
        draft, else `deposit_failed`, carrying `outcome`, which names the `approval` it acted on.
        Returns the event. Raises `ProjectError` for an unknown project. A deposit approved
        before the project was deleted still records its outcome."""
        detail = {key: value for key, value in outcome.items() if key not in ENVELOPE_KEYS}
        kind = DEPOSIT_RECORDED if recorded else DEPOSIT_FAILED
        event = self._event(project_id, kind, acted_for, caused_by, detail)
        with self._section(project_id, allow_deleted=True) as section:
            section.append([event])
        return event


def _repository(approval: Mapping[str, Any]) -> Any:
    """The repository an approval names: an approval recorded before repositories had an
    identifier of their own named re3data's."""
    return approval.get("repository_id") or approval.get("re3data_id")

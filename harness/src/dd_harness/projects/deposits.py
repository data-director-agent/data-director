"""What a project keeps of getting its data deposited: each validation of it against its
repository's requirements, each decision and confirmation a person makes before packaging, and
each deposit package built (docs/specs/deposit.md, invariants 8, 9 and 20 to 22)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from dd_harness.projects.rules import (
    DEPOSIT_CHECKS_CONFIRMED,
    DEPOSIT_ITEM_DECIDED,
    ENVELOPE_KEYS,
    PACKAGE_BUILT,
    PROJECT_VALIDATED,
    ProjectRules,
)
from dd_sdk.contract.models import Principal
from dd_sdk.evidence import INPUT_CANONICALISATION, canonicalise, input_hash


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
        self._append(project_id, PACKAGE_BUILT, acted_for, caused_by, {**detail, "digest": digest})
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

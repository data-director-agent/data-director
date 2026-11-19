"""What a project keeps of getting its data deposited: each validation of it against its
repository's requirements, each deposit package built, and each person's confirmation that the
checks before deposit were made (docs/specs/deposit.md, invariants 8, 9 and 21)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, Final

from dd_harness.projects.rules import (
    DEPOSIT_CHECKS_CONFIRMED,
    ENVELOPE_KEYS,
    INVENTORY_ADDED,
    PACKAGE_BUILT,
    PROJECT_VALIDATED,
    ProjectError,
    ProjectRules,
)
from dd_sdk.contract.models import Principal
from dd_sdk.evidence import INPUT_CANONICALISATION, canonicalise, input_hash

# What a person confirms before deposit, as C2 asks (docs/specs/deposit.md, invariant 21). The
# words are kept in the event, so the log says what was confirmed even if they change here.
DEPOSIT_CHECKS: Final = (
    "Ethics approval for collecting and sharing these data is in place, or none is needed.",
    "Advice on data protection has been taken where the data may hold personal data.",
    "The rights to share material from others, and the terms of any agreement, have been checked.",
)


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

    def confirm_checks(self, project_id: str, *, acted_for: Principal, caused_by: str) -> str:
        """Record `acted_for`'s confirmation of `DEPOSIT_CHECKS` for the inventory the project
        holds now, as a `deposit_checks_confirmed` event naming its digest
        (docs/specs/deposit.md, invariant 21). Returns the inventory's digest. Raises
        `ProjectError` for an unknown or deleted project, or one that holds no inventory yet,
        which records nothing."""
        with self._section(project_id) as section:
            added = [e for e in section.events() if e["event"] == INVENTORY_ADDED]
            if not added:
                raise ProjectError("the project holds no inventory to confirm the checks for")
            digest = str(added[-1]["digest"])
            detail = {"inventory_digest": digest, "statements": list(DEPOSIT_CHECKS)}
            section.append(
                [self._event(project_id, DEPOSIT_CHECKS_CONFIRMED, acted_for, caused_by, detail)]
            )
        return digest

    def checks_confirmation(self, project_id: str) -> dict[str, Any] | None:
        """The last `deposit_checks_confirmed` event, if it names the inventory the project holds
        now; None otherwise, since a confirmation is for the inventory it was made against.
        Raises `ProjectError` for an unknown project."""
        events = self.events(project_id)
        added = [e for e in events if e["event"] == INVENTORY_ADDED]
        confirmed = [e for e in events if e["event"] == DEPOSIT_CHECKS_CONFIRMED]
        if not added or not confirmed or confirmed[-1]["inventory_digest"] != added[-1]["digest"]:
            return None
        return dict(confirmed[-1])

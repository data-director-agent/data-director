"""The repository a researcher chose, and the requirements it resolved to
(docs/specs/deposit.md).

The repository a researcher chose is a `repository_chosen` event. It records each requirement
set the choice resolved to by reference and digest, and keeps the merged set as a blob, so that a
drafter and validation read exactly what was chosen. The last choice counts.
"""

from __future__ import annotations

from typing import Any

from dd_harness.projects.rules import REPOSITORY_CHOSEN, ProjectRules
from dd_harness.requirements import RE3DATA_ID, Requirements, RequirementsError
from dd_harness.sources import Sources
from dd_sdk.contract.models import Principal
from dd_sdk.evidence import INPUT_CANONICALISATION, canonicalise, input_hash


class RepositoryChoice(ProjectRules):
    """The rules of the repository a project is deposited in."""

    def choose_repository(
        self,
        project_id: str,
        re3data_id: str,
        *,
        registry: Sources,
        requirements: Requirements,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Record the repository a researcher chose by its re3data identifier, and the
        requirements it resolved to. Its name and declared metadata standards come from the
        latest re3data export `registry` pins, and the event names that record by `snapshot_ref`
        and content hash (docs/specs/deposit.md). Returns the merged set's digest. Raises
        `ProjectError` for an unknown project, `RequirementsError` for an identifier the export
        does not hold, and `SourceConfigError` if no built export is pinned."""
        self._require(project_id)
        if not RE3DATA_ID.fullmatch(re3data_id):
            raise RequirementsError(f"{re3data_id!r} is not a re3data identifier (r3d + 9 digits)")
        entry = registry.re3data(re3data_id)
        if entry is None:
            raise RequirementsError(
                f"the pinned re3data export holds no repository {re3data_id}; "
                "check the identifier at re3data.org"
            )
        resolved = requirements.resolve(entry.re3data_id, entry.name, entry.metadata_standards)
        merged = resolved.requirements()
        digest = input_hash(merged)
        self._keep_blob(project_id, digest, canonicalise(merged, INPUT_CANONICALISATION))
        self._append(
            project_id,
            REPOSITORY_CHOSEN,
            acted_for,
            caused_by,
            {
                "re3data_id": resolved.re3data_id,
                "repository_name": resolved.repository_name,
                "declared_standards": list(resolved.declared_standards),
                "snapshot_ref": entry.snapshot_ref,
                "record_hash": entry.content_hash,
                "record_canonicalisation": entry.canonicalisation,
                "requirement_sets": [s.describe() for s in resolved.sets],
                "digest": digest,
                "canonicalisation": INPUT_CANONICALISATION,
                "warnings": list(resolved.warnings),
            },
        )
        return digest

    def requirements(self, project_id: str) -> dict[str, Any] | None:
        """The merged requirements of the repository chosen last, or None if none has been."""
        return self._latest(project_id, REPOSITORY_CHOSEN)

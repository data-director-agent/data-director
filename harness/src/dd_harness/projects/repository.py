"""The repository a researcher chose, and the requirements it resolved to
(docs/specs/deposit.md).

The repository a researcher chose is a `repository_chosen` event. It records each requirement
set the choice resolved to by reference and digest, and the definition of the standard the merged
set follows by reference, digest and the codec of each serialisation
(docs/specs/metadata-standards.md, invariant 12), and keeps the merged set as a blob, so that a
drafter and validation read exactly what was chosen. The last choice counts.
"""

from __future__ import annotations

from typing import Any

from dd_harness.metadata_standards import registered
from dd_harness.projects.rules import REPOSITORY_CHOSEN, ProjectRules
from dd_harness.requirements import REPOSITORY_ID, Requirements, RequirementsError
from dd_harness.sources import Sources
from dd_sdk.contract.models import Principal
from dd_sdk.contract.requirements import legacy_term
from dd_sdk.evidence import INPUT_CANONICALISATION, canonicalise, input_hash


class RepositoryChoice(ProjectRules):
    """The rules of the repository a project is deposited in."""

    def choose_repository(
        self,
        project_id: str,
        repository_id: str,
        *,
        registry: Sources,
        requirements: Requirements,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Record the repository a researcher chose, by its re3data identifier or, for one
        re3data does not list, its DataCite one, and the requirements it resolved to. Its name
        and declared metadata standards come from the latest copy of that registry `registry`
        pins, and the event names that record by `snapshot_ref` and content hash
        (docs/specs/deposit.md). Returns the merged set's digest. Raises `ProjectError` for an
        unknown project, `RequirementsError` for an identifier no pinned copy holds, and
        `SourceConfigError` if no built re3data export is pinned."""
        self._require(project_id)
        if not REPOSITORY_ID.fullmatch(repository_id):
            raise RequirementsError(
                f"{repository_id!r} is neither a re3data identifier (r3d + 9 digits) nor a "
                "DataCite one (such as bl.york)"
            )
        entry = registry.repository(repository_id)
        if entry is None:
            raise RequirementsError(
                f"neither re3data nor DataCite, as pinned, holds a repository {repository_id}; "
                "check the identifier"
            )
        resolved = requirements.resolve(entry.repository_id, entry.name, entry.metadata_standards)
        merged = resolved.requirements()
        digest = input_hash(merged)
        standard = registered().by_uri(merged["conforms_to"])
        self._keep_blob(project_id, digest, canonicalise(merged, INPUT_CANONICALISATION))
        self._append(
            project_id,
            REPOSITORY_CHOSEN,
            acted_for,
            caused_by,
            {
                "repository_id": resolved.repository_id,
                "re3data_id": resolved.re3data_id,
                "repository_name": resolved.repository_name,
                "declared_standards": list(resolved.declared_standards),
                "snapshot_ref": entry.snapshot_ref,
                "record_hash": entry.content_hash,
                "record_canonicalisation": entry.canonicalisation,
                "requirement_sets": [s.describe() for s in resolved.sets],
                "standard": standard.definition.describe() if standard else None,
                "digest": digest,
                "canonicalisation": INPUT_CANONICALISATION,
                "warnings": list(resolved.warnings),
            },
        )
        return digest

    def requirements(self, project_id: str) -> dict[str, Any] | None:
        """The merged requirements of the repository chosen last, or None if none has been. A set
        kept before repositories had an identifier of their own is given its re3data one, and a
        field kept before terms were IRIs its `schema:` term (#1357)."""
        found = self._latest(project_id, REPOSITORY_CHOSEN)
        if found is None:
            return None
        if "repository_id" not in found and found.get("re3data_id"):
            found = {**found, "repository_id": found["re3data_id"]}
        if any("schema_org" in field for field in found.get("fields") or []):
            found = {**found, "fields": [legacy_term(field) for field in found["fields"]]}
        return found

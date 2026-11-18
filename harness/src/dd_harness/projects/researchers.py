"""The researchers of a project: facts from their own public ORCID records (docs/specs/projects.md).

A researcher may keep facts from their own public ORCID record in the project
(`dd_harness.orcid`): a `researcher_added` event names their iD, when the record was read, and the
digest of the `ResearcherRecord` they chose, kept as a blob in its `dd-input-json-v1` canonical
bytes (`add_researcher`). A person keeps only their own record, and keeping it again replaces what
they kept before. `researcher_withdrawn` (`withdraw_researcher`) stops it being given to agents;
like every event, what was kept stays in the log. `researchers` gives the records that stand, the
one kept first first, which the conductor puts into a `Message` and a `DraftRequest`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from dd_harness.projects.rules import (
    RESEARCHER_ADDED,
    RESEARCHER_WITHDRAWN,
    ProjectError,
    ProjectRules,
)
from dd_sdk.contract.models import Principal
from dd_sdk.contract.researcher import ResearcherRecord
from dd_sdk.evidence import INPUT_CANONICALISATION, canonicalise, input_hash


class Researchers(ProjectRules):
    """The rules of the researcher records a project keeps."""

    def add_researcher(
        self,
        project_id: str,
        record: Mapping[str, Any],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Keep `record`, a `ResearcherRecord` of what a person chose from their public ORCID
        record, in the project. Returns its digest.

        Raises `ProjectError` for an unknown project, a document that is not a `ResearcherRecord`,
        or a record of anyone but the person `acted_for` names: a person keeps only their own."""
        self._require(project_id)
        document = dict(record)
        try:
            ResearcherRecord.model_validate(document)
        except ValueError as exc:  # pydantic's ValidationError is a ValueError
            raise ProjectError(f"not a ResearcherRecord: {exc}") from exc
        if document["orcid_id"] != acted_for.principal_id:
            raise ProjectError("a person keeps only their own ORCID record")
        digest = input_hash(document)
        self._keep_blob(project_id, digest, canonicalise(document, INPUT_CANONICALISATION))
        self._append(
            project_id,
            RESEARCHER_ADDED,
            acted_for,
            caused_by,
            {
                "orcid_id": document["orcid_id"],
                "digest": digest,
                "canonicalisation": INPUT_CANONICALISATION,
                "record_retrieved_at": document["record_retrieved_at"],
            },
        )
        return digest

    def withdraw_researcher(
        self, project_id: str, orcid_id: str, *, acted_for: Principal, caused_by: str
    ) -> None:
        """Stop giving agents the record the person `orcid_id` names kept. Raises `ProjectError`
        for an unknown project, a record the project does not hold, or anyone withdrawing a
        record but their own."""
        if orcid_id != acted_for.principal_id:
            raise ProjectError("a person withdraws only their own ORCID record")
        if orcid_id not in self._researcher_digests(project_id):
            raise ProjectError("the project holds no ORCID record of theirs")
        self._append(project_id, RESEARCHER_WITHDRAWN, acted_for, caused_by, {"orcid_id": orcid_id})

    def researchers(self, project_id: str) -> list[dict[str, Any]] | None:
        """The `ResearcherRecord` each person kept and has not withdrawn, the one kept first
        first; None while there is none. Raises `UnknownProjectError` for an unknown project."""
        held = self._researcher_digests(project_id)
        records = [json.loads(self._blob(project_id, digest)) for digest in held.values()]
        return records or None

    def _researcher_digests(self, project_id: str) -> dict[str, str]:
        """The digest of the record that stands for each iD, in the order first kept."""
        held: dict[str, str] = {}
        for event in self.events(project_id):
            if event["event"] == RESEARCHER_ADDED:
                held[event["orcid_id"]] = event["digest"]
            elif event["event"] == RESEARCHER_WITHDRAWN:
                held.pop(event["orcid_id"], None)
        return held

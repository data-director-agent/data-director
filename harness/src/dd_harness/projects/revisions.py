"""A person's request that a drafter revise a document's latest version in the way they ask
(docs/specs/drafting.md, docs/specs/projects.md).

A request is a `document_revision_requested` event naming the version and the digest of the
text the person saw, with their words. Like an edit, it is refused, and the refusal recorded, if
it names anything but the document's latest text; a `questions` version, which is not the
document yet, cannot be revised. The request changes no version: the conductor gives it to the
drafter that is asked to revise (`DraftRequest.revise`), whose result is the next version.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dd_harness.projects.decisions import check_names, check_request
from dd_harness.projects.fold import DRAFT_STAGE, check_latest
from dd_harness.projects.rules import (
    DOCUMENT_REVISION_REQUESTED,
    ProjectRules,
    Refusal,
    Refused,
)
from dd_sdk.contract.models import DocumentVersionRef, Principal

if TYPE_CHECKING:
    from dd_harness.storage import ProjectSection


class Revisions(ProjectRules):
    """The rule of a person's request for changes to a document."""

    def request_revision(
        self,
        project_id: str,
        document_id: str,
        version: int,
        digest: str,
        instruction: str,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> DocumentVersionRef:
        """Record that `acted_for` asked for the latest version, whose text has `digest`, to be
        revised as `instruction` says. Returns the version named.

        Raises `ProjectError`, which records nothing, for a request malformed in itself, and
        `ChangeRefusedError`, which records the refusal, for one naming any text but the latest
        draft's."""
        check_names(document_id, digest)
        text = check_request(instruction)

        def change(section: ProjectSection) -> DocumentVersionRef | Refused:
            latest = check_latest(section.events(), document_id, version, digest, deciding=False)
            if isinstance(latest, Refused):
                return latest
            if latest["stage"] != DRAFT_STAGE:
                return Refused(
                    Refusal.NOT_A_DRAFT,
                    f"Version {version} only asks what the drafter needs before it writes the "
                    "document: answer its questions and ask for the document to be drafted.",
                    {"document_id": document_id, "version": version, "digest": digest},
                )
            detail = {
                "document_id": document_id,
                "version": version,
                "digest": digest,
                "instruction": text,
            }
            section.append(
                [self._event(project_id, DOCUMENT_REVISION_REQUESTED, acted_for, caused_by, detail)]
            )
            return DocumentVersionRef(document_id=document_id, version=version)

        return self._checked(project_id, acted_for, caused_by, change)

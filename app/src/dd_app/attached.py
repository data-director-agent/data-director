"""A document a turn attaches, kept in the conversation's project once
`dd_app.documentation_check.accept` has checked it (docs/specs/projects.md, Documentation). A
document attached as text is kept as it is; a Word document or PDF is kept as the file and the text
the harness reads from it inside the deployment (`dd_harness.projects.read_document_file`)."""

from __future__ import annotations

from dd_app.turn_body import AttachedDocument
from dd_harness.storage import ProjectHoldings
from dd_sdk.contract.models import Principal


def keep_attached(
    store: ProjectHoldings,
    project_id: str,
    document: AttachedDocument,
    acting_for: Principal,
    caused_by: str,
) -> str:
    """Keep the document in the project; returns the digest of its text."""
    if document.data is None:
        return store.add_documentation(
            project_id,
            document.name,
            document.media_type,
            document.text,
            acted_for=acting_for,
            caused_by=caused_by,
        )
    return store.add_document_file(
        project_id,
        document.name,
        document.media_type,
        document.data,
        acted_for=acting_for,
        caused_by=caused_by,
    )

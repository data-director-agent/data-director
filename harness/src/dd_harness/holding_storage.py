"""What the harness asks of a store for what a project holds about its data: its file inventory
and supporting documents (`dd_harness.projects.holdings`, docs/specs/projects.md).
`dd_harness.storage` composes it into `ProjectStorage` with the other areas of the project rules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from dd_sdk.contract.models import Principal


class ProjectHoldings(Protocol):
    """A project's file inventory and supporting documentation (`dd_harness.projects.holdings`)."""

    def add_inventory(
        self,
        project_id: str,
        inventory: Mapping[str, Any],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Add a `FileInventory`; returns its digest."""
        ...

    def inventory(self, project_id: str) -> dict[str, Any] | None:
        """The inventory added last, or None."""
        ...

    def add_documentation(
        self,
        project_id: str,
        name: str,
        media_type: str,
        text: str,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Add a supporting document's text; returns the SHA-256 of its UTF-8 text."""
        ...

    def documentation(self, project_id: str) -> list[dict[str, Any]]:
        """Each document the project holds, without its text, as a `DocumentationSummary`."""
        ...

    def add_document_file(
        self,
        project_id: str,
        name: str,
        media_type: str,
        data: bytes,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Add a Word or PDF document: the text read from it and the file itself. Returns the
        SHA-256 of the text, as `add_documentation` does."""
        ...

    def documentation_text(self, project_id: str, digest: str) -> str | None:
        """The text of the project's document with this digest, or None."""
        ...

    def documentation_source(self, project_id: str, digest: str) -> tuple[bytes, str] | None:
        """The file a document's text was read from, and its media type, or None if the
        document with this digest was attached as text or the project holds none."""
        ...

"""The retrieval seam in front of FAIRsharing's policy records. The types every registry's seam
shares (`Query`, `SnapshotRef`, `RegistryUnavailable`) are in `dd_sdk.registry`.

A protocol rather than an ABC, so a test fake need not import production code to be valid.
"""

from __future__ import annotations

from typing import Any, ClassVar, Protocol, runtime_checkable

from dd_agent_advisor_policy.records import PolicyRecord
from dd_sdk.registry import Query, SnapshotRef


@runtime_checkable
class Policies(Protocol):
    """FAIRsharing's policy records, or a copy of them."""

    def snapshot_ref(self) -> SnapshotRef: ...

    def search(self, query: Query) -> list[PolicyRecord]:
        """Policy records for a name, in the registry's order. Raises RegistryUnavailable when
        the registry cannot be asked."""
        ...

    def fetch(self, fairsharing_id: str) -> PolicyRecord | None: ...


class SourceRecord(Protocol):
    """A record the agent cites, whichever registry it came from: FAIRsharing's policy records,
    Open Policy Finder's (`opf.py`) and Crossref's journals (`crossref.py`). Each is evidence,
    hashed whole under `dd-json-document-v1`, and cited by `source_id`."""

    registry: ClassVar[str]

    @property
    def source_id(self) -> str: ...

    @property
    def source_uri(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def label(self) -> str: ...

    def document(self) -> dict[str, Any]: ...

    def content_hash(self) -> str: ...

    def prompt_text(self, limit: int = ...) -> str: ...

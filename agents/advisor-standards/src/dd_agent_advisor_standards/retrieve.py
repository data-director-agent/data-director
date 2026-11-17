"""The retrieval adapter interface: one seam in front of every way of reaching FAIRsharing.

Adapted from experiments/standards-advisor `registry/base.py`. A Protocol rather than an ABC:
the backends share a signature and nothing else worth inheriting, and a test fake need not
import production code to be valid. The types it uses (`Query`, `Hit`, `SnapshotRef`,
`RegistryUnavailable`) are shared through `dd_sdk.registry`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from dd_agent_advisor_standards.fairsharing.records import Record
from dd_sdk.registry import Hit, Query, SnapshotRef


@runtime_checkable
class RetrievalAdapter(Protocol):
    def snapshot_ref(self) -> SnapshotRef: ...

    def search(self, query: Query) -> list[Hit[Record]]:
        """Run one search. Raises RegistryUnavailable when the registry cannot be asked."""
        ...

    def fetch(self, fairsharing_id: str) -> Record | None: ...

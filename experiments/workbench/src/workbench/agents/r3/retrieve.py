"""The retrieval adapter interface: one seam in front of every way of reaching FAIRsharing.

Adapted from experiments/standards-advisor `registry/base.py`. A Protocol rather than an ABC:
the backends share a signature and nothing else worth inheriting, and a test fake need not
import production code to be valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from workbench.agents.r3.fairsharing.records import Record


class RegistryUnavailable(Exception):
    """The registry could not be searched. Not the same as an empty result (R3.6)."""


@dataclass(frozen=True)
class Query:
    text: str
    record_type: str | None = None
    limit: int = 10
    label: str = ""

    def describe(self) -> str:
        rt = f" [{self.record_type}]" if self.record_type else ""
        return f"{self.label or 'query'}: {self.text!r}{rt}"


@dataclass(frozen=True)
class Hit:
    record: Record
    lexical_score: float


@dataclass(frozen=True)
class SnapshotRef:
    """Which copy of the registry answered (standards-advisor §7.3)."""

    label: str
    stale: bool = False
    fetched_at: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_string(self) -> str:
        return self.label + (" (stale)" if self.stale else "")


@runtime_checkable
class RetrievalAdapter(Protocol):
    def snapshot_ref(self) -> SnapshotRef: ...

    def search(self, query: Query) -> list[Hit]:
        """Run one search. Raises RegistryUnavailable when the registry cannot be asked."""
        ...

    def fetch(self, fairsharing_id: str) -> Record | None: ...

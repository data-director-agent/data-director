"""The retrieval seam in front of FAIRsharing's policy records.

A protocol rather than an ABC, so a test fake need not import production code to be valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from dd_agent_policy.records import PolicyRecord


class RegistryUnavailable(Exception):
    """The registry could not be asked. Not the same as an empty result."""


@dataclass(frozen=True)
class Query:
    text: str
    limit: int = 10
    label: str = ""

    def describe(self) -> str:
        return f"{self.label or 'query'}: {self.text!r}"


@dataclass(frozen=True)
class SnapshotRef:
    """Which copy of the registry answered. It is the evidence's `snapshot_ref`, by which the
    harness's source check finds its own copy (ADR-0016)."""

    label: str
    stale: bool = False
    fetched_at: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_string(self) -> str:
        return self.label + (" (stale)" if self.stale else "")


@runtime_checkable
class Policies(Protocol):
    """FAIRsharing's policy records, or a copy of them."""

    def snapshot_ref(self) -> SnapshotRef: ...

    def search(self, query: Query) -> list[PolicyRecord]:
        """Policy records for a name, in the registry's order. Raises RegistryUnavailable when
        the registry cannot be asked."""
        ...

    def fetch(self, fairsharing_id: str) -> PolicyRecord | None: ...

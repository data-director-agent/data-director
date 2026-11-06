"""The retrieval seams: one in front of re3data, one in front of FAIRsharing's database records.

re3data is searched and fetched; it holds the facts Phase 3 asks about. FAIRsharing is only
fetched, by the identifier re3data cross-references, and adds its curators' account of access
and deposition conditions. Protocols rather than ABCs, so a test fake need not import production
code to be valid.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from dd_agent_advisor_repository.records import DatabaseRecord, Re3dataRecord


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
class Hit:
    record: Re3dataRecord
    lexical_score: float


@dataclass(frozen=True)
class SnapshotRef:
    """Which copy of a registry answered. It is the evidence's `snapshot_ref`, by which the
    harness's source check finds its own copy (docs/specs/grounding.md)."""

    label: str
    stale: bool = False
    fetched_at: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_string(self) -> str:
        return self.label + (" (stale)" if self.stale else "")


@runtime_checkable
class Repositories(Protocol):
    """re3data, as the pinned export (`snapshot.Re3dataRegistry`) or a test's copy."""

    def snapshot_ref(self) -> SnapshotRef: ...

    def credit(self) -> str:
        """The sentence that credits re3data in a statement."""
        ...

    def search(self, query: Query) -> list[Hit]:
        """Run one search. Raises RegistryUnavailable when the registry cannot be read."""
        ...

    def fetch(self, re3data_id: str) -> Re3dataRecord | None: ...

    def find(self, name: str) -> list[Re3dataRecord]:
        """The repositories named `name`, ignoring case (`find_by_name`): more than one when the
        name is ambiguous, and none rather than a guess."""
        ...


def find_by_name(records: Iterable[Re3dataRecord], name: str) -> list[Re3dataRecord]:
    """The records whose name is `name`, ignoring case; else those with it as an additional
    name. Sorted by identifier. Across all of re3data a name is not unique (institutional
    Dataverse and DSpace instances, shared acronyms), so the caller must not take the first."""
    wanted = name.casefold().strip()
    named = [r for r in records if r.name.casefold().strip() == wanted]
    found = named or [r for r in records if wanted in r.names()]
    return sorted(found, key=lambda r: r.re3data_id)


@runtime_checkable
class Databases(Protocol):
    """FAIRsharing's database records, or a copy of them."""

    def snapshot_ref(self) -> SnapshotRef: ...

    def fetch(self, fairsharing_id: str) -> DatabaseRecord | None: ...

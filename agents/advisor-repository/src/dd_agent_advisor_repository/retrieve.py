"""The retrieval seams: one in front of re3data, one in front of FAIRsharing's database records.

re3data is searched and fetched; it holds the facts Phase 3 asks about. FAIRsharing is only
fetched, by the identifier re3data cross-references, and adds its curators' account of access
and deposition conditions. Protocols rather than ABCs, so a test fake need not import production
code to be valid. The types every registry's seam shares (`Query`, `Hit`, `SnapshotRef`,
`RegistryUnavailable`) are in `dd_sdk.registry`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from dd_agent_advisor_repository.records import DatabaseRecord, Re3dataRecord
from dd_sdk.registry import Hit, Query, SnapshotRef


@runtime_checkable
class Repositories(Protocol):
    """re3data, as the pinned export (`snapshot.Re3dataRegistry`) or a test's copy."""

    def snapshot_ref(self) -> SnapshotRef: ...

    def credit(self) -> str:
        """The sentence that credits re3data in a statement."""
        ...

    def search(self, query: Query) -> list[Hit[Re3dataRecord]]:
        """Run one search. Raises RegistryUnavailable when the registry cannot be read."""
        ...

    def fetch(self, re3data_id: str) -> Re3dataRecord | None: ...

    def subjects(self) -> dict[str, str]:
        """Each DFG subject code the registry files a repository under, with its name
        (`dfg.vocabulary`)."""
        ...

    def with_subject(self, code: str) -> list[Re3dataRecord]:
        """Every repository filed under the DFG subject `code`, by identifier."""
        ...

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

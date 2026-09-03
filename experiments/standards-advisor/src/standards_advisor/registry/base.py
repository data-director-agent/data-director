"""§7.2 — one internal interface in front of every way of reaching the registry.

§7.1 lists four routes to FAIRsharing with different limits: some need an account, some cannot
search, some are unstable. Rather than let the pipeline talk to any one of them, everything
goes through `RegistryClient`, and adding or swapping a route is a configuration change.

A `Protocol`, not an ABC, for two reasons. The routes share no implementation worth inheriting
— a GraphQL client, an HTTP record fetcher and a file reader have the signature in common and
nothing else — and an ABC would invite a base class that accumulates behaviour the local-copy
route does not want. It also means a test fake need not import production code to be a valid
implementation.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import Field

from standards_advisor.models.candidates import RegistryQuery
from standards_advisor.models.common import Frozen, RegistrySnapshotRef, TermList


class RegistryTerm(Frozen):
    """One term from one of the registry's own lists.

    Fetched, never hard-coded. R3.5 forbids a built-in list of standards, and §5.2 extends that
    to the facets used to search for them: they are living vocabularies, and writing them into
    our code satisfies R3 today and breaks R3.5 by the next release.
    """

    value: str
    label: str | None = None
    list_name: TermList
    list_version: str | None = None


class RegistryRecord(Frozen):
    """A record as one route returned it."""

    registry_id: str
    name: str
    doi: str | None = None
    url: str | None = None
    record_type: str | None = None
    record_subtype: str | None = None
    """The curator-applied subtype §5.2 uses to separate ontologies from controlled
    vocabularies. See `ResourceRef.record_subtype` and the §1.2 stop condition."""
    status: str | None = None
    subjects: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    fields: dict[str, str] = Field(default_factory=dict)
    """Remaining scalar fields, flattened. What the §5.5 evidence check resolves against."""

    populated_fields: frozenset[str] = Field(default_factory=frozenset)
    """Which fields this route actually supplied — §7.2.

    Not the same as "which fields are non-empty". The routes carry different fields, so a
    ranking rule whose inputs are absent must be *skipped*, not scored zero; otherwise the same
    record ranks differently depending on which route fetched it, for no visible reason."""

    def supplies(self, *field_names: str) -> bool:
        """True only if this route supplied every named field. Used by the ranking rules."""
        return all(name in self.populated_fields for name in field_names)


class RegistrySearchResult(Frozen):
    """Hits, plus the query and snapshot that produced them.

    Carrying the query and snapshot back with the results makes §5.2's "every candidate
    remembers where it came from" hold by construction rather than by the caller remembering to
    attach it.
    """

    query: RegistryQuery
    snapshot: RegistrySnapshotRef
    records: list[RegistryRecord] = Field(default_factory=list)
    truncated: bool = False


@runtime_checkable
class RegistryClient(Protocol):
    """The four operations §7.2 names."""

    def snapshot(self) -> RegistrySnapshotRef:
        """Which copy of the registry this client is answering from (§7.3)."""
        ...

    def list_terms(self, list_name: TermList) -> Sequence[RegistryTerm]:
        """Fetch one of the registry's own controlled lists.

        Raises `RegistryUnavailable` when the list cannot be fetched. It must not return an
        empty sequence in that case — §5.2 requires failing noisily rather than quietly
        dropping a filter, and "the registry has no subjects" is a very different claim from
        "we could not ask it".
        """
        ...

    def search(self, query: RegistryQuery) -> RegistrySearchResult:
        """Run one search. Ranking, filtering for relevance and interpretation happen later."""
        ...

    def fetch_record(self, registry_id: str) -> RegistryRecord | None:
        """Look up one record by identifier, for checking that it still resolves."""
        ...

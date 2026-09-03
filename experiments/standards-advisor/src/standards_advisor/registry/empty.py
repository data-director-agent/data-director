"""The v0.1 registry: honest rather than convenient.

No route to FAIRsharing is implemented yet, and §1.2 says why that is the right order — three
assumptions about the real registry are stop conditions for the whole experiment and have not
been checked. So this client answers nothing, and says so everywhere the answer is visible.

What it deliberately does *not* do is pretend. `snapshot()` reports itself stale, so every v0.1
run states in its output document that it ran against no registry, and **every method that
would need a registry raises `RegistryUnavailable`** rather than returning an empty result.

That last choice is the whole point of this class, and it is worth being explicit about why.
Returning `[]` from `search()` would be much more convenient — the pipeline would flow straight
through with no error handling — but it would make the output document *lie*: the abstention
would read "we searched the registry and found nothing suitable", when nothing was searched.
"We looked and there is nothing" and "we could not look" are completely different statements to
a researcher, and R3.6 is about saying the true one. The queries themselves are still recorded
by the retrieve stage, so an abstention can say what it *would* have looked for.
"""

from __future__ import annotations

from collections.abc import Sequence

from standards_advisor.errors import RegistryUnavailable
from standards_advisor.models.candidates import RegistryQuery
from standards_advisor.models.common import RegistrySnapshotRef, TermList
from standards_advisor.registry.base import (
    RegistryRecord,
    RegistrySearchResult,
    RegistryTerm,
)


class EmptyRegistry:
    """A `RegistryClient` that has no registry behind it."""

    name = "empty"

    def snapshot(self) -> RegistrySnapshotRef:
        return RegistrySnapshotRef(
            version="unavailable",
            source="none",
            stale=True,
            retrieved_at=None,
        )

    def list_terms(self, list_name: TermList) -> Sequence[RegistryTerm]:
        raise RegistryUnavailable(
            f"no registry route is configured, so the {list_name} list cannot be fetched; "
            "R3.5 forbids substituting a built-in list"
        )

    def search(self, query: RegistryQuery) -> RegistrySearchResult:
        """Raise, because there is no registry to search.

        Not an empty result — see the module docstring. An empty result would be reported as
        "we searched and found nothing", which is untrue.
        """
        raise RegistryUnavailable(
            f"no registry route is configured, so the {query.kind} search did not run"
        )

    def fetch_record(self, registry_id: str) -> RegistryRecord | None:
        return None

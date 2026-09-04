"""FAIRsharing routes — NOT IMPLEMENTED AT v0.1.

This module exists to fix the shape of the seam and to record which §7.1 route maps onto which
`RegistryClient` method, so that implementing one is filling in a body rather than deciding an
interface.

Nothing here is written yet on purpose. §1.2 makes three properties of the real registry stop
conditions for the whole experiment, and none has been checked:

1. Whether records reliably carry a curator-applied **subtype** separating ontologies from
   controlled vocabularies — the one distinction R3 explicitly requires. The single permitted
   fallback is the declared serialisation (OWL → ontology, SKOS or OBO → vocabulary), which is
   still curated data rather than a model's judgement.
2. Whether the **subject and domain lists can be fetched by a program**. If they must be copied
   into our code, R3.5 cannot be met as written.
3. Whether **searching by subject finds anything outside the life sciences**.

Writing a client before checking those risks building carefully on an assumption that ends the
experiment.

## §7.1 routes and where each belongs

| Route | Account | Can search | Maps to |
|---|---|---|---|
| Direct record lookup (JSON at a record URL) | No | No | `fetch_record` only |
| Dated local copy | No | Yes | all four, offline; the C8 fallback |
| GraphQL | Yes | Yes | all four; the expected live route |
| REST | Yes | Yes | fallback if GraphQL proves unstable |

Direct record lookup needs no account, so it can be built while the access questions are open —
it is the natural first implementation, used for resolving identifiers we already have and for
checking that a recommended record still resolves.

Content is CC-BY-SA 4.0. Attribution is already handled, since every recommendation carries the
record's DOI and URL. Share-alike bites on redistribution, so publishing a harvested collection
or a fixture set built from one carries the obligation onto whatever we publish — §7.4's
recommendation is to publish only record identifiers and let others fetch the records.
"""

from __future__ import annotations

from collections.abc import Sequence

from standards_advisor.models.candidates import RegistryQuery
from standards_advisor.models.common import RegistrySnapshotRef, TermList
from standards_advisor.registry.base import (
    RegistryRecord,
    RegistrySearchResult,
    RegistryTerm,
)

_NOT_YET = (
    "FAIRsharing access is not implemented at v0.1; see this module's docstring for the three "
    "§1.2 stop conditions that must be checked against the live registry first"
)


class FairsharingRegistry:
    """Placeholder for the live routes. Every method raises."""

    name = "fairsharing"

    def snapshot(self) -> RegistrySnapshotRef:
        raise NotImplementedError(_NOT_YET)

    def list_terms(self, list_name: TermList) -> Sequence[RegistryTerm]:
        raise NotImplementedError(_NOT_YET)

    def search(self, query: RegistryQuery) -> RegistrySearchResult:
        raise NotImplementedError(_NOT_YET)

    def fetch_record(self, registry_id: str) -> RegistryRecord | None:
        raise NotImplementedError(_NOT_YET)

"""The v0.1 registry, and why it refuses rather than returning nothing.

The distinction these tests pin down is the difference between two statements a researcher would
act on differently: "we looked and there is nothing suitable" and "we could not look". §5.2
requires failing noisily rather than quietly dropping a filter, and R3.6 is about saying the
true one.
"""

from __future__ import annotations

import pytest

from standards_advisor.errors import ConfigError, RegistryUnavailable
from standards_advisor.models.candidates import RegistryQuery
from standards_advisor.models.common import RecommendationKind, TermList
from standards_advisor.registry import get_registry
from standards_advisor.registry.base import RegistryClient
from standards_advisor.registry.empty import EmptyRegistry
from standards_advisor.registry.fairsharing import FairsharingRegistry
from tests.fakes import FakeRegistry, make_record


def test_the_empty_registry_reports_itself_stale():
    """So every v0.1 run says so in its output document, not just in a log (§7.3)."""
    snapshot = EmptyRegistry().snapshot()
    assert snapshot.stale is True
    assert snapshot.version == "unavailable"
    assert snapshot.retrieved_at is None


def test_listing_terms_raises_rather_than_returning_an_empty_list():
    """An empty list would read as "the registry has no subjects" — a different claim entirely,
    and one that would let a future tier-2 profiler silently proceed with no facets (R3.5)."""
    with pytest.raises(RegistryUnavailable, match=r"R3\.5"):
        EmptyRegistry().list_terms(TermList.SUBJECT)


def test_searching_raises_rather_than_returning_no_results():
    """Returning `[]` would make the abstention say "we searched and found nothing"."""
    query = RegistryQuery(kind=RecommendationKind.OPEN_FORMAT)
    with pytest.raises(RegistryUnavailable):
        EmptyRegistry().search(query)


def test_fetching_a_record_returns_none():
    assert EmptyRegistry().fetch_record("FAIRsharing.aaa") is None


def test_the_live_route_is_an_explicit_stub():
    """Not written yet on purpose — §1.2's three stop conditions come first."""
    with pytest.raises(NotImplementedError, match="stop conditions"):
        FairsharingRegistry().snapshot()


def test_routes_are_selected_by_configuration():
    assert isinstance(get_registry("empty"), EmptyRegistry)
    assert isinstance(get_registry("fairsharing"), FairsharingRegistry)


def test_an_unknown_route_names_the_ones_that_exist():
    with pytest.raises(ConfigError, match="known routes"):
        get_registry("nope")


def test_every_implementation_satisfies_the_protocol():
    """Including the test fake, which is why the interface is a Protocol and not an ABC —
    a fake should not have to inherit from production code to be a valid implementation."""
    for client in (EmptyRegistry(), FairsharingRegistry(), FakeRegistry()):
        assert isinstance(client, RegistryClient)


def test_a_search_result_carries_its_query_and_snapshot_back():
    """§5.2: every candidate must remember where it came from.

    Carrying them back with the hits makes that hold by construction, rather than depending on
    the caller remembering to attach them.
    """
    registry = FakeRegistry({"open_format": [make_record("FAIRsharing.csv", "CSV")]})
    query = RegistryQuery(kind=RecommendationKind.OPEN_FORMAT, facets={"format": ["csv"]})
    result = registry.search(query)

    assert result.query == query
    assert result.snapshot.version == "2026-09-01"
    assert len(result.records) == 1


def test_a_record_knows_which_fields_its_route_supplied():
    record = make_record("FAIRsharing.aaa", "A", fields={"licence": "CC-BY-4.0"})
    assert record.supplies("licence")
    assert not record.supplies("adopter_count")
    assert not record.supplies("licence", "adopter_count")

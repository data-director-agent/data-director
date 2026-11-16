"""Crossref's journal records, and resolving a journal to its publisher (`journals.py`,
`resolve.py`). The live route is faked with recorded answers; the network is blocked."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from dd_agent_advisor_policy.classes import Actor, ActorRole
from dd_agent_advisor_policy.journals import (
    CrossrefJournals,
    Journal,
    issn,
    publisher_forms,
    without_legal_form,
)
from dd_agent_advisor_policy.resolve import (
    JournalAmbiguous,
    JournalFound,
    Unknown,
    names,
    publishers,
    resolve_journal,
)
from dd_agent_advisor_policy.retrieve import RegistryUnavailable, SnapshotRef

DATA = Path(__file__).parent / "data"
RECORD = json.loads((DATA / "crossref-journal-0022-1694.json").read_text(encoding="utf-8"))
SEARCH = json.loads(
    (DATA / "crossref-journals-query-journal-of-hydrology.json").read_text(encoding="utf-8")
)


def _live(handler: Any) -> CrossrefJournals:
    return CrossrefJournals(client=httpx.Client(transport=httpx.MockTransport(handler)))


def journal(title: str, publisher: str | None, *issns: str) -> Journal:
    return Journal(
        id=f"https://api.crossref.org/journals/{issns[0]}",
        title=title,
        publisher=publisher,
        issns=list(issns),
    )


class FakeJournals:
    def __init__(self, journals: list[Journal]) -> None:
        self.journals = journals

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="fake-crossref")

    def get(self, value: str) -> Journal | None:
        return next((j for j in self.journals if issn(value) in j.issns), None)

    def find(self, title: str) -> list[Journal]:
        return [j for j in self.journals if j.matches(title)]


# --- the live route ---------------------------------------------------------------------------


def test_a_journal_is_read_by_its_issn() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/journals/0022-1694")
        return httpx.Response(200, json=RECORD)

    found = _live(handler).get("0022-1694")
    assert found is not None
    assert (found.title, found.publisher, found.issns) == (
        "Journal of Hydrology",
        "Elsevier",
        ["0022-1694"],
    )
    assert found.id == "https://api.crossref.org/journals/0022-1694"


def test_a_title_search_keeps_exact_titles_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["query"] == "journal of  HYDROLOGY"
        return httpx.Response(200, json=SEARCH)

    # Crossref's search is fuzzy: "Journal of Contaminant Hydrology" and others come back too.
    found = _live(handler).find("journal of  HYDROLOGY")
    assert [j.title for j in found] == ["Journal of Hydrology"]


def test_a_live_failure_is_unavailable_and_an_unknown_issn_is_none() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(RegistryUnavailable):
        _live(down).find("Journal of Hydrology")
    assert _live(lambda r: httpx.Response(404, text="Resource not found.")).get("0000-0000") is None
    assert _live(lambda r: httpx.Response(200, json=RECORD)).get("not an ISSN") is None
    with pytest.raises(RegistryUnavailable):
        _live(lambda r: httpx.Response(500)).get("0022-1694")
    with pytest.raises(RegistryUnavailable):
        _live(lambda r: httpx.Response(200, text="<html>")).find("Journal of Hydrology")
    assert _live(lambda r: httpx.Response(200)).snapshot_ref().label.startswith("crossref:live:")


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("Elsevier BV", "Elsevier"),
        ("Elsevier B.V.", "Elsevier"),
        ("Acme Publishing Co. Ltd", "Acme Publishing"),
        ("Springer Science and Business Media LLC", "Springer Science and Business Media"),
        ("Copernicus GmbH", "Copernicus"),
        ("Public Library of Science (PLoS)", "Public Library of Science (PLoS)"),
        ("Ltd", "Ltd"),
    ],
)
def test_a_publishers_legal_form_is_left_out(given: str, expected: str) -> None:
    assert without_legal_form(given) == expected


def test_a_publisher_is_searched_without_a_bracketed_imprint() -> None:
    assert publisher_forms("Wiley (Blackwell Publishing)") == [
        "Wiley (Blackwell Publishing)",
        "Wiley",
    ]
    assert publisher_forms("Elsevier BV") == ["Elsevier BV", "Elsevier"]
    assert publisher_forms("Elsevier") == ["Elsevier"]


# --- resolving a journal ----------------------------------------------------------------------

LETTERS = journal("Acme Reports", "Acme B.V.", "1234-5678")
LETTERS_ONLINE = journal("Acme Reports", "Acme BV", "8765-432X")
NAMESAKE = journal("Acme Reports", "Other Press Ltd", "1111-2222")


def test_a_journal_given_by_issn_is_found_with_its_publisher() -> None:
    actor = Actor(role=ActorRole.JOURNAL, name="AR", issn="12345678")
    found = resolve_journal(actor, FakeJournals([LETTERS, NAMESAKE]))
    assert isinstance(found, JournalFound) and found.journals == (LETTERS,)
    assert names(actor, found) == ["AR", "Acme Reports"]
    assert publishers(found) == ["Acme B.V.", "Acme"]


def test_records_of_one_title_and_one_publisher_are_one_journal() -> None:
    actor = Actor(role=ActorRole.JOURNAL, name="acme reports")
    found = resolve_journal(actor, FakeJournals([LETTERS, LETTERS_ONLINE]))
    # "Acme B.V." and "Acme BV" are one publisher once the legal form is left out.
    assert isinstance(found, JournalFound) and len(found.journals) == 2


def test_one_title_from_different_publishers_is_asked_about() -> None:
    actor = Actor(role=ActorRole.JOURNAL, name="Acme Reports")
    found = resolve_journal(actor, FakeJournals([LETTERS, NAMESAKE]))
    assert isinstance(found, JournalAmbiguous)
    assert {j.publisher for j in found.candidates} == {"Acme B.V.", "Other Press Ltd"}


def test_an_unknown_journal_is_searched_as_given_and_other_roles_are_not_looked_up() -> None:
    journals = FakeJournals([LETTERS])
    unknown = Actor(role=ActorRole.JOURNAL, name="Unheard Of")
    assert isinstance(resolve_journal(unknown, journals), Unknown)
    assert names(unknown, Unknown()) == ["Unheard Of"] and publishers(Unknown()) == []
    funder = Actor(role=ActorRole.FUNDER, name="Acme Reports")
    assert isinstance(resolve_journal(funder, journals), Unknown)

"""Open Policy Finder and Crossref over a mocked transport, answering from hand-written fixtures.

The fixtures (`data/opf-*.json`, `data/crossref-journal-stoten.json`) follow the shape of the
Sherpa v2 API, which Jisc says the Open Policy Finder platform replicates, and Crossref's journals
API. They were written by hand, not recorded: no key was at hand. TODO(#302) replace them with
answers recorded by `dd-mcp-opf check --record`.

The mocked `/retrieve` refuses, with a 400 as Jisc documents, a filter that uses an operator or
field the documentation does not list for the item type, or more than three conditions.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import httpx

from dd_agent_advisor_policy.crossref import CrossrefJournals
from dd_agent_advisor_policy.opf import OpenPolicyFinder

DATA = Path(__file__).with_name("data")
KEY = "test-opf-key"


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((DATA / name).read_text(encoding="utf-8"))
    return data


NERC_FUNDER = load("opf-funder-nerc.json")
STOTEN = load("opf-publication-stoten.json")
ELSEVIER = load("opf-publisher-elsevier.json")
CROSSREF_STOTEN = load("crossref-journal-stoten.json")
EMPTY: dict[str, Any] = {"items": []}

NERC_OPF = "https://openpolicyfinder.jisc.ac.uk/funder/1201"
STOTEN_OPF = "https://openpolicyfinder.jisc.ac.uk/publication/2290"
ELSEVIER_OPF = "https://openpolicyfinder.jisc.ac.uk/publisher/30"
STOTEN_CROSSREF = "https://api.crossref.org/journals/0048-9697"


# The filter fields Jisc documents for each item type, and its operators.
FIELDS = {
    "funder": {"name", "name_name", "acronym", "name_acronym", "country", "id", "funderid"},
    "publisher": {"name", "name_name", "acronym", "name_acronym", "country", "id"},
    "publication": {"title", "title_title", "acronym", "title_acronym", "issn", "id"},
}
OPERATORS = {"equals", "contains word", "gte", "lte"}


def conditions(request: httpx.Request) -> list[tuple[str, str, str]]:
    """The conditions of a /retrieve request's filter."""
    return [tuple(c) for c in json.loads(request.url.params.get("filter", "[]"))]


def refusal(request: httpx.Request) -> str | None:
    """Why the documented API would refuse this /retrieve request, or None."""
    item_type = request.url.params.get("item-type", "")
    found = conditions(request)
    if not 1 <= len(found) <= 3:
        return f"{len(found)} conditions"
    for field, operator, _ in found:
        if field not in FIELDS.get(item_type, set()) or operator not in OPERATORS:
            return f"unsupported condition {field!r} {operator!r}"
    return None


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def fits(request: httpx.Request, name: str, acronyms: Sequence[str] = ()) -> bool:
    """Whether every condition of the request holds for a record with this name and acronyms."""
    for field, _, value in conditions(request):
        wanted = value.casefold()
        if "acronym" in field:
            if wanted not in {a.casefold() for a in acronyms}:
                return False
        elif wanted not in _words(name):
            return False
    return True


def opf_handler(
    seen: list[httpx.Request] | None = None,
    extra: dict[tuple[str, str], dict[str, Any]] | None = None,
    status: int = 200,
) -> Callable[[httpx.Request], httpx.Response]:
    """Answers searches for NERC, Elsevier and Science of the Total Environment, and reads by
    ISSN 0048-9697 and publisher 30. `extra` adds answers by (item type, record name)."""
    named: list[tuple[str, str, Sequence[str], dict[str, Any]]] = [
        *((t, n, (), answer) for (t, n), answer in (extra or {}).items()),
        ("funder", "Natural Environment Research Council", ("NERC",), NERC_FUNDER),
        ("publication", "Science of the Total Environment", ("STOTEN",), STOTEN),
        ("publisher", "Elsevier", (), ELSEVIER),
    ]

    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": "no"})
        if request.url.path == "/retrieve_by_id":
            item_type = request.url.params.get("item-type")
            ident = request.url.params.get("identifier")
            if (item_type, ident) in (("publication", "0048-9697"), ("publication", "2290")):
                return httpx.Response(200, json=STOTEN)
            if (item_type, ident) == ("publisher", "30"):
                return httpx.Response(200, json=ELSEVIER)
            return httpx.Response(404, json={"error": "not found"})
        if (why := refusal(request)) is not None:
            return httpx.Response(400, json={"error": why})
        item_type = request.url.params.get("item-type")
        for kind, name, acronyms, answer in named:
            if kind == item_type and fits(request, name, acronyms):
                return httpx.Response(200, json=answer)
        return httpx.Response(200, json=EMPTY)

    return handle


def crossref_handler(
    seen: list[httpx.Request] | None = None, status: int = 200
) -> Callable[[httpx.Request], httpx.Response]:
    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if status != 200:
            return httpx.Response(status)
        if request.url.path == "/journals/0048-9697":
            return httpx.Response(200, json=CROSSREF_STOTEN)
        if request.url.path == "/journals":
            query = (request.url.params.get("query") or "").casefold()
            items = [CROSSREF_STOTEN["message"]] if "total environment" in query else []
            return httpx.Response(200, json={"status": "ok", "message": {"items": items}})
        return httpx.Response(404, text="Resource not found.")

    return handle


def opf(handler: Callable[[httpx.Request], httpx.Response] | None = None) -> OpenPolicyFinder:
    client = httpx.Client(transport=httpx.MockTransport(handler or opf_handler()))
    return OpenPolicyFinder(KEY, client=client)


def opf_finding_nothing() -> OpenPolicyFinder:
    """Open Policy Finder with a key, answering every search with no record."""
    return opf(lambda request: httpx.Response(200, json=EMPTY))


def crossref(
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
) -> CrossrefJournals:
    client = httpx.Client(transport=httpx.MockTransport(handler or crossref_handler()))
    return CrossrefJournals(client=client)

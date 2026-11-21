"""Open Policy Finder and Crossref over a mocked transport, answering from hand-written fixtures.

The fixtures (`data/opf-*.json`, `data/crossref-journal-stoten.json`) follow the shape of the
Sherpa v2 API, which Jisc says the Open Policy Finder platform replicates, and Crossref's journals
API. They were written by hand, not recorded: no key was at hand. TODO(#302) replace them with
answers recorded by `python -m dd_agent_advisor_policy.opf check --record`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
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


def _words(request: httpx.Request) -> tuple[str, str]:
    """The item type and the searched text of a /retrieve request."""
    item_type = request.url.params.get("item-type", "")
    [[_, _, text]] = json.loads(request.url.params.get("filter", '[["", "", ""]]'))
    return item_type, text.casefold().removeprefix("the ")


def opf_handler(
    seen: list[httpx.Request] | None = None,
    extra: dict[tuple[str, str], dict[str, Any]] | None = None,
    status: int = 200,
) -> Callable[[httpx.Request], httpx.Response]:
    """Answers searches for NERC, Elsevier and Science of the Total Environment, and reads by
    ISSN 0048-9697 and publisher 30. `extra` adds answers by (item type, searched text)."""

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
        item_type, text = _words(request)
        if extra and (item_type, text) in extra:
            return httpx.Response(200, json=extra[(item_type, text)])
        if item_type == "funder" and text in (
            "nerc",
            "natural environment research council",
        ):
            return httpx.Response(200, json=NERC_FUNDER)
        if item_type == "publication" and text == "science of the total environment":
            return httpx.Response(200, json=STOTEN)
        if item_type == "publisher" and text == "elsevier":
            return httpx.Response(200, json=ELSEVIER)
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

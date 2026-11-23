"""DOAJ's journal search API, and each journal as a record of its open access terms.

- `GET https://doaj.org/api/v4/search/journals/issn:<issn>` reads one journal by ISSN;
- `GET https://doaj.org/api/v4/search/journals/bibjson.title:"<title>"` searches by title.

Neither needs an account. DOAJ limits its API to two requests a second, with bursts of five, so a
busy answer (429) is retried once after a pause. Each request names this package and where its
source is, and never anything about the person or project the journal came from; a caller may add
its operators' contact address.

A record keeps what DOAJ says about the journal's open access terms and leaves out its editorial
and indexing details. It holds no integers (a year or a price is a string), so that it hashes the
same after a round trip through a format whose numbers are doubles. Lists are sorted. Any
transport failure, error status or unreadable answer raises `DoajUnavailableError`; an ISSN DOAJ
does not list is None.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from urllib.parse import quote

import httpx

API_BASE = "https://doaj.org/api/v4/search/journals/"
JOURNAL_PAGE = "https://doaj.org/toc/{issn}"
SOURCE_URL = "https://github.com/data-director-agent/data-director"
TIMEOUT_S = 20.0
SEARCH_ROWS = 5
# DOAJ's rate limit is two requests a second: one retry after a pause, then the lookup fails.
RETRY_PAUSE_S = 1.0
ISSN = re.compile(r"^\d{4}-?\d{3}[\dX]$")
# A plain address: nothing that could end the User-Agent's comment or start another header.
ADDRESS = re.compile(r"[^\s@<>();,\"\\]+@[^\s@<>();,\"\\]+\.[^\s@<>();,\"\\]+")
# What the journal links to about its terms, by DOAJ's own key.
PAGES = ("journal", "oa_statement", "license_terms", "author_instructions")


class DoajUnavailableError(Exception):
    """DOAJ could not be asked, or gave an answer that cannot be read. The message says why and
    holds nothing the caller sent but the ISSN or title."""


def normal_issn(value: str) -> str | None:
    """`value` as `NNNN-NNNC`, or None if it is not an ISSN."""
    text = value.strip().upper()
    if not ISSN.match(text):
        return None
    digits = text.replace("-", "")
    return f"{digits[:4]}-{digits[4:]}"


def user_agent(contact: str | None = None) -> str:
    """This package's User-Agent, with `mailto:contact` when a contact address is given. Raises
    `ValueError` when `contact` is not one plain address."""
    if contact is not None and not ADDRESS.fullmatch(contact):
        raise ValueError(f"{contact!r} is not an e-mail address")
    try:
        ver = version("data-director-mcp-doaj")
    except PackageNotFoundError:  # pragma: no cover - run from a source tree without installing
        ver = "0"
    mailto = f"; mailto:{contact}" if contact else ""
    return f"data-director-mcp-doaj/{ver} (+{SOURCE_URL}{mailto})"


def _text(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _flag(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _texts(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return sorted({t for t in (_text(v) for v in values) if t})


def _part(bibjson: dict[str, Any], key: str) -> dict[str, Any]:
    value = bibjson.get(key)
    return value if isinstance(value, dict) else {}


def _licences(bibjson: dict[str, Any]) -> list[dict[str, str]]:
    found = {
        (t, _text(item.get("url")) or "")
        for item in bibjson.get("license") or []
        if isinstance(item, dict) and (t := _text(item.get("type")))
    }
    return [{"type": t, "url": url} for t, url in sorted(found)]


def _charges(apc: dict[str, Any]) -> list[str]:
    """Each highest charge as `<amount> <currency>`, such as `2477 USD`."""
    found = {
        f"{price} {currency}"
        for item in apc.get("max") or []
        if isinstance(item, dict)
        and (price := _text(item.get("price")))
        and (currency := _text(item.get("currency")))
    }
    return sorted(found)


def _pages(bibjson: dict[str, Any]) -> dict[str, str]:
    ref = _part(bibjson, "ref")
    return {key: url for key in PAGES if (url := _text(ref.get(key)))}


def journal_record(result: dict[str, Any]) -> dict[str, Any] | None:
    """One DOAJ search result as a record of the journal's open access terms. None if it has no
    identifier, title or ISSN."""
    bibjson = result.get("bibjson")
    if not isinstance(bibjson, dict):
        return None
    doaj_id, title = _text(result.get("id")), _text(bibjson.get("title"))
    issns = [i for i in (normal_issn(str(bibjson.get(k) or "")) for k in ("eissn", "pissn")) if i]
    if not doaj_id or not title or not issns:
        return None
    publisher, copyright_ = _part(bibjson, "publisher"), _part(bibjson, "copyright")
    deposit, preservation = _part(bibjson, "deposit_policy"), _part(bibjson, "preservation")
    apc, waiver = _part(bibjson, "apc"), _part(bibjson, "waiver")
    return {
        "id": doaj_id,
        "url": JOURNAL_PAGE.format(issn=issns[0]),
        "title": title,
        "alternative_title": _text(bibjson.get("alternative_title")),
        "eissn": normal_issn(str(bibjson.get("eissn") or "")),
        "pissn": normal_issn(str(bibjson.get("pissn") or "")),
        "publisher": _text(publisher.get("name")),
        "publisher_country": _text(publisher.get("country")),
        "licences": _licences(bibjson),
        "author_retains_copyright": _flag(copyright_.get("author_retains")),
        "copyright_url": _text(copyright_.get("url")),
        "deposit_policy": {
            "has_policy": _flag(deposit.get("has_policy")),
            "services": _texts(deposit.get("service")),
            "url": _text(deposit.get("url")),
        },
        "preservation": {
            "has_preservation": _flag(preservation.get("has_preservation")),
            "services": _texts(preservation.get("service")),
        },
        "apc": {
            "has_apc": _flag(apc.get("has_apc")),
            "highest": _charges(apc),
            "url": _text(apc.get("url")),
        },
        "has_waiver": _flag(waiver.get("has_waiver")),
        "oa_start": _text(bibjson.get("oa_start")),
        "pages": _pages(bibjson),
        "subjects": sorted(
            {
                t
                for s in bibjson.get("subject") or []
                if isinstance(s, dict) and (t := _text(s.get("term")))
            }
        ),
        "last_updated": _text(result.get("last_updated")),
    }


class Doaj:
    """DOAJ's public API. One instance serves concurrent callers: it keeps no per-call state.
    `client` replaces the HTTP client in tests; `sleep` the pause before a retry."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        contact: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self.user_agent = user_agent(contact)
        self._sleep = sleep

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=TIMEOUT_S, follow_redirects=True)
        return self._client

    def _get(self, query: str, rows: int) -> list[dict[str, Any]]:
        url = API_BASE + quote(query, safe=":")
        params = {"pageSize": str(rows)}
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        try:
            resp = self._http().get(url, params=params, headers=headers)
            if resp.status_code == 429:
                self._sleep(RETRY_PAUSE_S)
                resp = self._http().get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise DoajUnavailableError(f"DOAJ: {type(exc).__name__}") from None
        if resp.status_code != 200:
            raise DoajUnavailableError(f"DOAJ: HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError:
            raise DoajUnavailableError("DOAJ: an answer that is not JSON") from None
        results = body.get("results") if isinstance(body, dict) else None
        if not isinstance(results, list):
            raise DoajUnavailableError("DOAJ: an answer with no results")
        return [r for r in results if isinstance(r, dict)]

    def by_issn(self, issn: str) -> dict[str, Any] | None:
        """The journal with this ISSN, print or electronic, or None if DOAJ does not list it or
        `issn` is not an ISSN."""
        wanted = normal_issn(issn)
        if wanted is None:
            return None
        for result in self._get(f"issn:{wanted}", 2):
            record = journal_record(result)
            if record and wanted in (record["eissn"], record["pissn"]):
                return record
        return None

    def search(self, title: str, rows: int = SEARCH_ROWS) -> list[dict[str, Any]]:
        """Journals whose title matches `title`, in DOAJ's order, at most `rows`."""
        words = " ".join(title.replace('"', " ").split())
        if not words:
            return []
        found = [journal_record(r) for r in self._get(f'bibjson.title:"{words}"', rows)]
        unique = {r["id"]: r for r in found if r is not None}
        return list(unique.values())

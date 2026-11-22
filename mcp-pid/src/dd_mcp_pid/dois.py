"""DOIs, resolved by the registration agency that holds them: DataCite or Crossref.

Each agency's REST API answers for its own DOIs only, and both need no account
(https://support.datacite.org/docs/api, https://www.crossref.org/documentation/retrieve-metadata/rest-api/).
A DOI the agency does not hold is not found there; the caller may ask the other.

Both are cut to one record shape, `DoiRecord`, so a citing agent reads either the same way. The
publication year is kept as text, so no record holds an integer.
"""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict

from dd_mcp_pid.http import Http, UnavailableError

DATACITE_API = "https://api.datacite.org/dois"
# A record names its first creators only, so a work with thousands of authors stays small.
MAX_CREATORS = 25
CROSSREF_API = "https://api.crossref.org/works"

# A DOI: the 10. prefix, a registrant code and any suffix without spaces.
DOI = re.compile(r"^10\.\d{4,9}/\S+$")
DOI_RESOLVER = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)

type Agency = Literal["DataCite", "Crossref"]


def bare_doi(value: str) -> str | None:
    """`value` as a bare, lower-case DOI (DOIs are case-insensitive), or None if it is not one."""
    doi = DOI_RESOLVER.sub("", value.strip()).lower()
    return doi if DOI.match(doi) else None


class DoiRecord(BaseModel):
    """What a DOI names, as its registration agency describes it, cut to what linking needs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    doi: str
    """The bare DOI, lower-case: what the record is cited by."""
    agency: Agency
    title: str | None = None
    type: str | None = None
    """DataCite's resourceTypeGeneral (such as Dataset), or Crossref's type (such as
    journal-article)."""
    publisher: str | None = None
    publication_year: str | None = None
    creators: list[str] = []
    """The first `MAX_CREATORS` creators, as the agency names them."""
    url: str | None = None
    """Where the DOI resolves to, as the agency records it."""

    def document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _first_text(values: Any, key: str | None = None) -> str | None:
    for value in values or []:
        text = value.get(key) if key and isinstance(value, dict) else value
        if isinstance(text, str) and text.strip():
            return " ".join(text.split())
    return None


def _year(value: Any) -> str | None:
    return str(value) if isinstance(value, int | str) and str(value).strip() else None


def _datacite_record(doi: str, attrs: dict[str, Any]) -> DoiRecord:
    publisher = attrs.get("publisher")
    if isinstance(publisher, dict):  # the API gives an object when asked with publisher=true
        publisher = publisher.get("name")
    return DoiRecord(
        doi=str(attrs.get("doi") or doi).lower(),
        agency="DataCite",
        title=_first_text(attrs.get("titles"), "title"),
        type=(attrs.get("types") or {}).get("resourceTypeGeneral") or None,
        publisher=publisher if isinstance(publisher, str) and publisher else None,
        publication_year=_year(attrs.get("publicationYear")),
        creators=[c["name"] for c in attrs.get("creators") or [] if c.get("name")][:MAX_CREATORS],
        url=attrs.get("url") or None,
    )


def _crossref_name(author: dict[str, Any]) -> str | None:
    if author.get("name"):
        return str(author["name"])
    family, given = author.get("family"), author.get("given")
    if family and given:
        return f"{family}, {given}"
    return family or given or None


def _crossref_record(doi: str, msg: dict[str, Any]) -> DoiRecord:
    parts = (msg.get("issued") or {}).get("date-parts") or [[]]
    year = parts[0][0] if parts and parts[0] else None
    return DoiRecord(
        doi=str(msg.get("DOI") or doi).lower(),
        agency="Crossref",
        title=_first_text(msg.get("title")),
        type=msg.get("type") or None,
        publisher=msg.get("publisher") or None,
        publication_year=_year(year),
        creators=[n for a in msg.get("author") or [] if (n := _crossref_name(a))][:MAX_CREATORS],
        url=msg.get("URL") or None,
    )


class DataCite:
    """DataCite's REST API, for DOIs DataCite holds."""

    def __init__(self, http: Http | None = None, contact: str | None = None) -> None:
        self.http = http or Http(
            "DataCite", headers={"Accept": "application/vnd.api+json"}, contact=contact
        )

    def get(self, doi: str) -> DoiRecord | None:
        """The DOI's record, or None when DataCite holds no such DOI."""
        resp = self.http.get(f"{DATACITE_API}/{quote(doi, safe='/')}")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise UnavailableError(f"DataCite: HTTP {resp.status_code}")
        try:
            attrs = self.http.json(resp)["data"]["attributes"]
            return _datacite_record(doi, attrs)
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            raise UnavailableError(f"DataCite: an answer that cannot be read ({exc})") from None


class Crossref:
    """Crossref's REST API, for DOIs Crossref holds."""

    def __init__(self, http: Http | None = None, contact: str | None = None) -> None:
        self.http = http or Http("Crossref", contact=contact)

    def get(self, doi: str) -> DoiRecord | None:
        """The DOI's record, or None when Crossref holds no such DOI."""
        resp = self.http.get(f"{CROSSREF_API}/{quote(doi, safe='/')}")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise UnavailableError(f"Crossref: HTTP {resp.status_code}")
        try:
            return _crossref_record(doi, self.http.json(resp)["message"])
        except (KeyError, TypeError, AttributeError, ValueError, IndexError) as exc:
            raise UnavailableError(f"Crossref: an answer that cannot be read ({exc})") from None

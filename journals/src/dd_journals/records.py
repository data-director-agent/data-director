"""A journal as `dd_journals` keeps it, projected from an OpenAlex source record."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dd_journals.issn import normal_issn

PORTAL_URL = "https://portal.issn.org/resource/ISSN/{issn}"


@dataclass(frozen=True)
class Journal:
    """One journal, identified by its linking ISSN (ISSN-L).

    `issns` holds every ISSN OpenAlex gives it, the ISSN-L among them, sorted. `title` is
    OpenAlex's display name, which may differ from the ISSN key title. `publisher` is the name of
    OpenAlex's host organisation. `country` is an ISO 3166-1 alpha-2 code. `works_count` is how
    many works OpenAlex counts in it, used only to order search results.
    """

    issn_l: str
    issns: tuple[str, ...]
    title: str
    alternate_titles: tuple[str, ...]
    abbreviated_title: str | None
    publisher: str | None
    country: str | None
    homepage: str | None
    is_in_doaj: bool
    is_oa: bool
    openalex_id: str
    works_count: int

    @property
    def portal_url(self) -> str:
        """The journal's record in the ISSN Portal, the ISSN International Centre's register."""
        return PORTAL_URL.format(issn=self.issn_l)

    def as_dict(self) -> dict[str, Any]:
        """The journal as it is stored: one line of `journals.jsonl`."""
        return {
            "issn_l": self.issn_l,
            "issns": list(self.issns),
            "title": self.title,
            "alternate_titles": list(self.alternate_titles),
            "abbreviated_title": self.abbreviated_title,
            "publisher": self.publisher,
            "country": self.country,
            "homepage": self.homepage,
            "is_in_doaj": self.is_in_doaj,
            "is_oa": self.is_oa,
            "openalex_id": self.openalex_id,
            "works_count": self.works_count,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Journal:
        """A journal from one line of `journals.jsonl`."""
        return cls(
            issn_l=str(data["issn_l"]),
            issns=tuple(data["issns"]),
            title=str(data["title"]),
            alternate_titles=tuple(data["alternate_titles"]),
            abbreviated_title=data["abbreviated_title"],
            publisher=data["publisher"],
            country=data["country"],
            homepage=data["homepage"],
            is_in_doaj=bool(data["is_in_doaj"]),
            is_oa=bool(data["is_oa"]),
            openalex_id=str(data["openalex_id"]),
            works_count=int(data["works_count"]),
        )


def _text(value: object) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def from_openalex(source: Mapping[str, Any]) -> Journal | None:
    """The journal an OpenAlex source record describes, or None when it is not a journal or has
    no ISSN-L. ISSNs that are not shaped like one are left out."""
    if source.get("type") != "journal":
        return None
    issn_l = normal_issn(str(source.get("issn_l") or ""))
    title = _text(source.get("display_name"))
    if issn_l is None or title is None:
        return None
    issns = {issn_l} | {i for raw in source.get("issn") or [] if (i := normal_issn(str(raw)))}
    alternates = {t for raw in source.get("alternate_titles") or [] if (t := _text(raw))}
    alternates.discard(title)
    return Journal(
        issn_l=issn_l,
        issns=tuple(sorted(issns)),
        title=title,
        alternate_titles=tuple(sorted(alternates)),
        abbreviated_title=_text(source.get("abbreviated_title")),
        publisher=_text(source.get("host_organization_name")),
        country=_text(source.get("country_code")),
        homepage=_text(source.get("homepage_url")),
        is_in_doaj=bool(source.get("is_in_doaj")),
        is_oa=bool(source.get("is_oa")),
        openalex_id=str(source.get("id") or ""),
        works_count=int(source.get("works_count") or 0),
    )

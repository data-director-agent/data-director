"""A fake ORCID public API (docs/specs/projects.md).

`FakeOrcidRegistry` serves public records over an `httpx.MockTransport`, so a test of bringing
researcher facts into a project needs no network. `sample_record` is the public record of the
researcher in ORCID's own documentation, Josiah Carberry, in the shape of ORCID's v3.0 JSON:
every section `dd_harness.orcid.normalise` reads, an email address it must leave out, and an
item marked limited that it must skip.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from dd_harness.orcid import ORCID_MEDIA_TYPE, PUBLIC_APIS

SAMPLE_ID = "0000-0002-1825-0097"


def _date(year: int | None) -> dict[str, Any] | None:
    return {"year": {"value": str(year)}, "month": None, "day": None} if year else None


def _affiliation(
    key: str, code: int, organisation: str, role: str, start: int, end: int | None, **extra: Any
) -> dict[str, Any]:
    return {
        "summaries": [
            {
                key: {
                    "put-code": code,
                    "department-name": extra.get("department"),
                    "role-title": role,
                    "start-date": _date(start),
                    "end-date": _date(end),
                    "organization": {
                        "name": organisation,
                        "disambiguated-organization": extra.get("disambiguated"),
                    },
                    "visibility": extra.get("visibility", "public"),
                }
            }
        ]
    }


def _work(
    code: int, title: str, year: int, doi: str | None, kind: str = "journal-article"
) -> dict[str, Any]:
    ids = (
        [
            {
                "external-id-type": "doi",
                "external-id-value": doi,
                "external-id-url": {"value": f"https://doi.org/{doi}"},
                "external-id-relationship": "self",
            }
        ]
        if doi
        else []
    )
    return {
        "work-summary": [
            {
                "put-code": code,
                "title": {"title": {"value": title}},
                "type": kind,
                "publication-date": _date(year),
                "journal-title": {"value": "Journal of Psychoceramics"},
                "external-ids": {"external-id": ids},
                "visibility": "public",
            }
        ]
    }


def sample_record(orcid_id: str = SAMPLE_ID, host: str = "sandbox.orcid.org") -> dict[str, Any]:
    """A public record in ORCID's v3.0 JSON, for the researcher `orcid_id` names."""
    brown = {
        "disambiguated-organization-identifier": "https://ror.org/05gq02987",
        "disambiguation-source": "ROR",
    }
    return {
        "orcid-identifier": {"uri": f"https://{host}/{orcid_id}", "path": orcid_id, "host": host},
        "person": {
            "name": {
                "given-names": {"value": "Josiah"},
                "family-name": {"value": "Carberry"},
                "credit-name": None,
                "visibility": "public",
            },
            "other-names": {
                "other-name": [
                    {"put-code": 11, "content": "J. S. Carberry", "visibility": "public"}
                ]
            },
            "biography": {
                "content": "Josiah Carberry is a fictitious person used as an example.",
                "visibility": "public",
            },
            "researcher-urls": {
                "researcher-url": [
                    {
                        "put-code": 21,
                        "url-name": "Wikipedia",
                        "url": {"value": "https://en.wikipedia.org/wiki/Josiah_S._Carberry"},
                        "visibility": "public",
                    },
                    {
                        "put-code": 22,
                        "url-name": "Not a web address",
                        "url": {"value": "example dot org"},
                        "visibility": "public",
                    },
                ]
            },
            # Public, and still never kept (C2).
            "emails": {
                "email": [{"email": "josiah@example.org", "visibility": "public", "verified": True}]
            },
            "addresses": {
                "address": [{"put-code": 31, "country": {"value": "US"}, "visibility": "public"}]
            },
            "keywords": {
                "keyword": [
                    {"put-code": 41, "content": "psychoceramics", "visibility": "public"},
                    {"put-code": 42, "content": "ionian philology", "visibility": "public"},
                    {
                        "put-code": 43,
                        "content": "kept for trusted parties",
                        "visibility": "limited",
                    },
                ]
            },
            "external-identifiers": {
                "external-identifier": [
                    {
                        "put-code": 51,
                        "external-id-type": "Scopus Author ID",
                        "external-id-value": "7004530145",
                        "external-id-url": {
                            "value": "https://www.scopus.com/authid/detail.uri?authorId=7004530145"
                        },
                        "visibility": "public",
                    }
                ]
            },
        },
        "activities-summary": {
            "employments": {
                "affiliation-group": [
                    _affiliation(
                        "employment-summary",
                        101,
                        "Brown University",
                        "Professor of Psychoceramics",
                        1979,
                        None,
                        department="Psychoceramics",
                        disambiguated=brown,
                    ),
                    _affiliation(
                        "employment-summary",
                        102,
                        "Wesleyan University",
                        "Lecturer",
                        1970,
                        1978,
                        visibility="limited",
                    ),
                ]
            },
            "educations": {
                "affiliation-group": [
                    _affiliation(
                        "education-summary",
                        111,
                        "Brown University",
                        "PhD",
                        1960,
                        1965,
                        disambiguated=brown,
                    )
                ]
            },
            "works": {
                "group": [
                    _work(201, "The Psychoceramics of Cracked Pots", 2008, "10.5555/12345678"),
                    _work(202, "Cracked pottery: a dataset", 2021, "10.5555/87654321", "data-set"),
                    _work(203, "Untitled notes", 1990, None, "other"),
                ]
            },
            "fundings": {
                "group": [
                    {
                        "funding-summary": [
                            {
                                "put-code": 301,
                                "title": {"title": {"value": "Fractures in Ionian pottery"}},
                                "type": "grant",
                                "start-date": _date(2019),
                                "end-date": None,
                                "organization": {
                                    "name": "National Science Foundation",
                                    "disambiguated-organization": {
                                        "disambiguated-organization-identifier": (
                                            "https://doi.org/10.13039/100000001"
                                        ),
                                        "disambiguation-source": "FUNDREF",
                                    },
                                },
                                "external-ids": {
                                    "external-id": [
                                        {
                                            "external-id-type": "grant_number",
                                            "external-id-value": "NSF-1234567",
                                            "external-id-relationship": "self",
                                        }
                                    ]
                                },
                                "visibility": "public",
                            }
                        ]
                    }
                ]
            },
        },
    }


@dataclass
class FakeOrcidRegistry:
    """ORCID's public API in memory: a record for each iD in `records`, and 404 for any other.
    `issuer` picks the API it answers as; it defaults to the sandbox, as `FakeIdentityProvider`
    does. `requests` counts the records read, so a test can see that one was read again."""

    issuer: str = "https://sandbox.orcid.org"
    records: dict[str, dict[str, Any]] = field(default_factory=lambda: {SAMPLE_ID: sample_record()})
    requests: int = 0
    # The status every request is answered with instead, to play an ORCID that is down.
    failing: int | None = None

    def transport(self) -> httpx.MockTransport:
        api = PUBLIC_APIS[self.issuer.rstrip("/")]

        def answer(request: httpx.Request) -> httpx.Response:
            self.requests += 1
            if self.failing is not None:
                return httpx.Response(self.failing)
            url = str(request.url.copy_with(query=None))
            if request.method != "GET" or not url.startswith(api + "/"):
                return httpx.Response(404)
            if request.headers.get("accept") != ORCID_MEDIA_TYPE:
                return httpx.Response(406)
            orcid_id, _, rest = url.removeprefix(api + "/").partition("/")
            if rest != "record" or orcid_id not in self.records:
                return httpx.Response(404)
            return httpx.Response(200, json=self.records[orcid_id])

        return httpx.MockTransport(answer)

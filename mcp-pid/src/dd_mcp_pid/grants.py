"""Grants, found by award number in Crossref's grant records and in the OpenAIRE Graph.

Crossref holds a record for each grant a funder registered a DOI for (`type: grant`), and finds
them by award number (https://www.crossref.org/documentation/research-nexus/grants/). Many funders
register none, UKRI among them, so the OpenAIRE Graph's projects are asked as well
(https://graph.openaire.eu/docs/apis/graph-api/, API v4). OpenAIRE's metadata is CC BY 4.0, with
OpenAIRE credited as the source.

Both are cut to one record shape, `GrantRecord`, which holds no integers: an award's dates are
ISO text. Only the award number is sent to either; a funder's name narrows the answers here
(`grant_server.py`), never upstream.

OpenAIRE answers 60 anonymous requests an hour. With the operators' contact address it is sent
as `mailto`; with a refresh token (`DD_OPENAIRE_REFRESH_TOKEN`), each request carries an access
token issued from it, which raises the limit to 7,200 an hour
(https://graph.openaire.eu/docs/apis/terms/). An access token lasts an hour and is issued again
when it runs out; when one cannot be issued, the request goes anonymously.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict

from dd_mcp_pid.http import Http, UnavailableError

CROSSREF_WORKS = "https://api.crossref.org/works"
OPENAIRE_PROJECTS = "https://api.openaire.eu/graph/v4/projects"
OPENAIRE_TOKEN = "https://services.openaire.eu/uoa-user-management/api/users/getAccessToken"
OPENAIRE_PROJECT_PAGE = "https://explore.openaire.eu/search/project?projectId="
FUNDER_DOI = "https://doi.org/"
# At most this many candidates from each source: a grant number shared more widely than this is
# not one a researcher can choose from.
ROWS = 20
OPENAIRE_FIELDS = "id,code,acronym,title,startDate,endDate,funding"
# How long an access token is used for, in seconds, unless OpenAIRE says less: it lasts an hour.
TOKEN_LIFE_S = 3300.0
# An award number: printable, without the separators of either API's filter syntax.
AWARD = re.compile(r"^[^\s,|]+(?: [^\s,|]+)*$")
MAX_AWARD = 100

type Source = Literal["Crossref", "OpenAIRE"]


def award_number(value: str) -> str | None:
    """`value` as an award number to ask for, or None when it cannot be one."""
    award = " ".join(value.split())
    if not award or len(award) > MAX_AWARD or not AWARD.match(award):
        return None
    return award


class GrantRecord(BaseModel):
    """A grant, as Crossref or OpenAIRE describes it, cut to what a funding reference needs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    """What the record is cited by: the grant DOI as a URL, or the OpenAIRE project's page."""
    source: Source
    award: str | None = None
    title: str | None = None
    acronym: str | None = None
    funder: str | None = None
    funder_short_name: str | None = None
    funder_ids: list[str] = []
    """The funder's Crossref Funder IDs (as doi.org URLs) and ROR ids, where the source has them."""
    funding_stream: str | None = None
    """The funder's scheme or programme the grant was made under."""
    start_date: str | None = None
    end_date: str | None = None
    doi: str | None = None
    """The grant's DOI, bare and lower-case, where it has one."""
    openaire_id: str | None = None

    def document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return " ".join(value.split()) or None


def _date(value: Any) -> str | None:
    """A Crossref date (`{"date-parts": [[y, m, d]]}`) as ISO text, as far as it is given."""
    try:
        parts = [int(p) for p in value["date-parts"][0] if p is not None][:3]
    except TypeError, ValueError, IndexError, KeyError:
        return None
    if not parts:
        return None
    return "-".join([f"{parts[0]:04d}", *(f"{p:02d}" for p in parts[1:])])


def _funder_ids(ids: Any) -> list[str]:
    out: list[str] = []
    for entry in ids or []:
        value, kind = _text(entry.get("id")), str(entry.get("id-type") or "").upper()
        if value and kind == "DOI":
            out.append(FUNDER_DOI + value.lower().removeprefix(FUNDER_DOI))
        elif value and kind == "ROR":
            out.append(value)
    return out


def crossref_grant(msg: dict[str, Any]) -> GrantRecord:
    """A Crossref grant work as a record."""
    doi = str(msg["DOI"]).lower()
    project = (msg.get("project") or [{}])[0]
    funding = (project.get("funding") or [{}])[0]
    funder = funding.get("funder") or {}
    titles = [t.get("title") for t in project.get("project-title") or []]
    return GrantRecord(
        id=FUNDER_DOI + doi,
        source="Crossref",
        award=_text(msg.get("award")),
        title=next((t for t in map(_text, titles) if t), None),
        funder=_text(funder.get("name")) or _text(msg.get("publisher")),
        funder_ids=_funder_ids(funder.get("id")),
        funding_stream=_text(funding.get("scheme")),
        start_date=_date(project.get("award-start")),
        end_date=_date(project.get("award-end")),
        doi=doi,
    )


def openaire_project(result: dict[str, Any]) -> GrantRecord:
    """An OpenAIRE Graph project as a record."""
    ident = str(result["id"])
    funding = result.get("funding") or {}
    funder = funding.get("funder") or {}
    pid = funder.get("pid")
    ror = _text(pid.get("value")) if isinstance(pid, dict) and pid.get("scheme") == "ror" else None
    stream = funding.get("level0") or {}
    return GrantRecord(
        id=OPENAIRE_PROJECT_PAGE + quote(ident, safe=":_"),
        source="OpenAIRE",
        award=_text(result.get("code")),
        title=_text(result.get("title")),
        acronym=_text(result.get("acronym")),
        funder=_text(funder.get("name")),
        funder_short_name=_text(funder.get("shortname")),
        funder_ids=[ror] if ror else [],
        funding_stream=_text(stream.get("name")) or _text(stream.get("description")),
        start_date=_text(result.get("startDate")),
        end_date=_text(result.get("endDate")),
        openaire_id=ident,
    )


class CrossrefGrants:
    """Crossref's grant records, by DOI or by award number."""

    def __init__(self, http: Http | None = None, contact: str | None = None) -> None:
        self.http = http or Http("Crossref", contact=contact)

    def _read[T](self, resp: Any, read: Callable[[Any], T]) -> T:
        if resp.status_code != 200:
            raise UnavailableError(f"Crossref: HTTP {resp.status_code}")
        try:
            return read(self.http.json(resp)["message"])
        except (KeyError, TypeError, AttributeError, ValueError, IndexError) as exc:
            raise UnavailableError(f"Crossref: an answer that cannot be read ({exc})") from None

    def by_doi(self, doi: str) -> GrantRecord | None:
        """The grant with this DOI, or None when Crossref holds no grant by it."""
        resp = self.http.get(f"{CROSSREF_WORKS}/{quote(doi, safe='/')}")
        if resp.status_code == 404:
            return None
        return self._read(resp, lambda m: crossref_grant(m) if m.get("type") == "grant" else None)

    def by_award(self, award: str) -> list[GrantRecord]:
        """Every grant Crossref holds under this award number, up to `ROWS`."""
        params = {"filter": f"type:grant,award.number:{award}", "rows": str(ROWS)}
        resp = self.http.get(CROSSREF_WORKS, params=params)
        return self._read(resp, lambda m: [crossref_grant(item) for item in m["items"]])


@dataclass
class AccessToken:
    """Access tokens issued from an OpenAIRE refresh token, each kept until shortly before it
    runs out. `clock` replaces the time in tests."""

    refresh_token: str = field(repr=False)
    http: Http = field(default_factory=lambda: Http("OpenAIRE tokens", pauses=()))
    clock: Callable[[], float] = time.monotonic
    _token: str | None = field(default=None, init=False, repr=False)
    _until: float = field(default=0.0, init=False, repr=False)

    def get(self) -> str | None:
        """A current access token, or None when none can be issued."""
        if self._token is not None and self.clock() < self._until:
            return self._token
        self._token = None
        try:
            resp = self.http.get(OPENAIRE_TOKEN, params={"refreshToken": self.refresh_token})
            body = self.http.json(resp) if resp.status_code == 200 else {}
        except UnavailableError:
            return None
        token = body.get("access_token") if isinstance(body, dict) else None
        if not isinstance(token, str) or not token:
            return None
        try:
            life = min(TOKEN_LIFE_S, float(body.get("expires_in", "")) - 60)
        except TypeError, ValueError:
            life = TOKEN_LIFE_S
        self._token, self._until = token, self.clock() + life
        return token


class OpenAireGraph:
    """The OpenAIRE Graph's projects, by award number (grant agreement code)."""

    def __init__(
        self,
        http: Http | None = None,
        contact: str | None = None,
        token: AccessToken | None = None,
    ) -> None:
        self.http = http or Http("OpenAIRE", contact=contact)
        self.contact = contact
        self.token = token
        self.anonymous = False
        """Whether the last request went without a token although one was configured."""

    def by_award(self, award: str) -> list[GrantRecord]:
        """Every project OpenAIRE holds under this code, up to `ROWS`."""
        params = {"filter": f"code:{award}", "page_size": str(ROWS), "select": OPENAIRE_FIELDS}
        if self.contact:
            params["mailto"] = self.contact
        headers: dict[str, str] = {}
        access = self.token.get() if self.token is not None else None
        self.anonymous = self.token is not None and access is None
        if access:
            headers["Authorization"] = f"Bearer {access}"
        resp = self.http.get(OPENAIRE_PROJECTS, params=params, headers=headers)
        if resp.status_code != 200:
            raise UnavailableError(f"OpenAIRE: HTTP {resp.status_code}")
        try:
            results = self.http.json(resp)["results"] or []
            return [openaire_project(r) for r in results]
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            raise UnavailableError(f"OpenAIRE: an answer that cannot be read ({exc})") from None

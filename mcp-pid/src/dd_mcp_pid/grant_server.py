"""The `grants` server: `resolve_grant`, an award number to every grant it may name.

A grant number alone can name several funders' grants, so every candidate is answered and none is
chosen: more than one record means the person must say which is theirs. The rules:

1. A grant DOI is asked of Crossref alone, which holds it or does not.
2. Any other award is asked of Crossref's grant records and then of the OpenAIRE Graph's projects.
   A project OpenAIRE holds for a grant Crossref already answered with (the same award, from the
   same funder) is left out, so that one grant is one candidate, cited by its DOI; the funder's
   short name it gives is kept on Crossref's record.
3. A funder's name, where given, keeps the candidates from a funder of that name, short name or
   funding stream. It is matched here and never sent. When it matches none, every candidate is kept
   and the summary says so.
4. When one source fails and the other answers, the answer says which failed; when both fail, the
   call is an error.

The schema is written out, as in `tools.py`, because a client pins it. No record holds an integer.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

from mcp_types import CallToolResult, Tool

from dd_mcp_pid.caching import OfflineError
from dd_mcp_pid.dois import bare_doi
from dd_mcp_pid.grants import CrossrefGrants, GrantRecord, OpenAireGraph, award_number
from dd_mcp_pid.http import UnavailableError
from dd_mcp_pid.tools import Registry, found, records_schema, text

_TEXT = {"type": "string"}
_OPTIONAL_TEXT = {"type": ["string", "null"]}

GRANT_RECORD = {
    "type": "object",
    "properties": {
        "id": _TEXT,
        "source": {"type": "string", "enum": ["Crossref", "OpenAIRE"]},
        "award": _OPTIONAL_TEXT,
        "title": _OPTIONAL_TEXT,
        "acronym": _OPTIONAL_TEXT,
        "funder": _OPTIONAL_TEXT,
        "funder_short_name": _OPTIONAL_TEXT,
        "funder_ids": {"type": "array", "items": _TEXT},
        "funding_stream": _OPTIONAL_TEXT,
        "start_date": _OPTIONAL_TEXT,
        "end_date": _OPTIONAL_TEXT,
        "doi": _OPTIONAL_TEXT,
        "openaire_id": _OPTIONAL_TEXT,
    },
    "required": [
        "id",
        "source",
        "award",
        "title",
        "acronym",
        "funder",
        "funder_short_name",
        "funder_ids",
        "funding_stream",
        "start_date",
        "end_date",
        "doi",
        "openaire_id",
    ],
    "additionalProperties": False,
}

RESOLVE_GRANT = Tool(
    name="resolve_grant",
    description=(
        "Every grant an award number may name: from Crossref's grant records and, for awards "
        "with no grant DOI, the OpenAIRE Graph's projects. Each gives the title, funder, funder "
        "identifiers, funding stream and dates, and is cited by its grant DOI or OpenAIRE project "
        "page. More than one record means the number is ambiguous: ask the person which grant is "
        "theirs, and never choose for them. A funder's name, where given, narrows the records "
        "and is not sent anywhere. No records if neither source holds the award."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "award": {
                "type": "string",
                "description": "The award or grant number as the funder gives it, or a grant DOI.",
            },
            "funder": {
                "type": "string",
                "description": "The funder's name, short name or scheme, if known.",
            },
        },
        "required": ["award"],
        "additionalProperties": False,
    },
    output_schema=records_schema(GRANT_RECORD, at_most_one=False),
)


def _words(name: str | None) -> str:
    """`name` lower-cased, without accents, punctuation or a leading 'the', for comparing."""
    if not name:
        return ""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    words = "".join(c if c.isalnum() else " " for c in plain).split()
    return " ".join(words[1:] if words[:1] == ["the"] else words)


def _alike(a: str | None, b: str | None) -> bool:
    """Whether one name is the other, or the start or a whole run of words of it."""
    x, y = _words(a), _words(b)
    if not x or not y:
        return False
    short, long = sorted((x, y), key=len)
    return f" {short} " in f" {long} "


def _same_grant(crossref: GrantRecord, project: GrantRecord) -> bool:
    if _words(crossref.award) != _words(project.award):
        return False
    if set(crossref.funder_ids) & set(project.funder_ids):
        return True
    return _alike(crossref.funder, project.funder)


def _merged(crossref: list[GrantRecord], projects: list[GrantRecord]) -> list[GrantRecord]:
    """Crossref's grants, each with the funder's short name of the OpenAIRE project for the same
    grant where Crossref gives none, then the projects for any other grant."""
    out = []
    for grant in crossref:
        twin = next((p for p in projects if _same_grant(grant, p)), None)
        if twin is not None and grant.funder_short_name is None:
            grant = grant.model_copy(update={"funder_short_name": twin.funder_short_name})
        out.append(grant)
    return out + [p for p in projects if not any(_same_grant(c, p) for c in crossref)]


def _from_funder(record: GrantRecord, funder: str) -> bool:
    names = (record.funder, record.funder_short_name, record.funding_stream)
    return any(_alike(funder, name) for name in names)


@dataclass
class Answer:
    """What the sources gave for one award: the candidates, and what the summary must add."""

    records: list[GrantRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GrantSources:
    crossref: CrossrefGrants
    openaire: OpenAireGraph | None
    offline: bool = False
    """Ask neither source (`DD_PID_OFFLINE`): grants are searches, which are not cached."""

    def resolve(self, award: str, funder: str | None) -> Answer:
        """Every candidate for `award`, by the rules above."""
        if self.offline:
            raise OfflineError(
                "Grants: this server is offline (DD_PID_OFFLINE), so Crossref and OpenAIRE "
                "were not asked"
            )
        doi = bare_doi(award)
        if doi is not None:
            record = self.crossref.by_doi(doi)
            return Answer([record] if record else [])
        answer = Answer()
        failed: list[str] = []
        try:
            answer.records = self.crossref.by_award(award)
        except UnavailableError as exc:
            failed.append(str(exc))
        if self.openaire is not None:
            try:
                projects = self.openaire.by_award(award)
            except UnavailableError as exc:
                failed.append(str(exc))
            else:
                answer.records = _merged(answer.records, projects)
                if self.openaire.anonymous:
                    answer.notes.append(
                        "OpenAIRE was asked anonymously: no access token was issued"
                    )
        sources = 1 + (self.openaire is not None)
        if failed and len(failed) == sources:
            raise UnavailableError("; ".join(failed))
        answer.notes += [f"{reason}, so its grants are missing" for reason in failed]
        if funder:
            kept = [r for r in answer.records if _from_funder(r, funder)]
            if kept:
                answer.records = kept
            elif answer.records:
                answer.notes.append(f"none is from a funder named {funder!r}, so all are listed")
        return answer


def _summary(record: GrantRecord) -> str:
    by = ", ".join(x for x in (record.funder, record.funding_stream) if x) or "funder not given"
    return f"{record.title or '(untitled)'} ({by}; {record.source}: {record.id})"


def grant_registry(sources: GrantSources) -> Registry:
    """The `grants` server."""

    def resolve_grant(arguments: dict[str, Any]) -> CallToolResult:
        given = arguments.get("award")
        award = award_number(given) if isinstance(given, str) else None
        if award is None:
            return text(
                "Not an award number: give it as the funder does, or a grant DOI.", error=True
            )
        named = arguments.get("funder")
        funder = " ".join(named.split()) if isinstance(named, str) else ""
        answer = sources.resolve(award, funder or None)
        listed = "; ".join(_summary(r) for r in answer.records) or "none"
        many = " More than one: ask which is theirs." if len(answer.records) > 1 else ""
        notes = "".join(f" Note: {n}." for n in answer.notes)
        return found(
            [r.document() for r in answer.records],
            f"{len(answer.records)} grant(s) for award {award!r}: {listed}.{many}{notes}",
        )

    return Registry("grants", (RESOLVE_GRANT,), {"resolve_grant": resolve_grant})

"""A researcher's public ORCID record, read for them and only when they ask
(docs/specs/projects.md, docs/specs/policy-and-identity.md).

A person signed in with ORCID may bring facts from their own public record into a project: their
name, affiliations, keywords, works, funding and the rest of what they have made public. Nothing
is kept until they choose:

- `fetch_record` reads the record from ORCID's public API, which needs no credential and returns
  only what the holder made public. Only the signed-in person's own iD is read (`orcid_path`).
- `normalise` turns ORCID's JSON into a `ResearcherRecord` document. Email addresses are never
  taken, even public ones (C2); an item ORCID marks anything but public is skipped; at most
  `WORKS_OFFERED` works are offered, the most recent first, and `works_omitted` counts the rest.
- `select` keeps only the sections and items the person ticked, by section name and ORCID
  put-code. A caller sends a choice, never the facts, and the record is read again before it is
  kept, so what a project holds is always ORCID's own words.

A record that cannot be read raises `OrcidUnavailableError`: the network, ORCID, or an iD it does
not know, never a content problem of a run.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Final

import httpx

from dd_sdk.contract.models import AffiliationKind, Principal, ResearcherRecord

FETCH_TIMEOUT_S: Final = 10.0
# The most works offered, so that an agent's input stays bounded; the rest are counted.
WORKS_OFFERED: Final = 50
# ORCID's public API for each issuer it signs people in as. Any other issuer has none.
PUBLIC_APIS: Final = {
    "https://orcid.org": "https://pub.orcid.org/v3.0",
    "https://sandbox.orcid.org": "https://pub.sandbox.orcid.org/v3.0",
}
ORCID_MEDIA_TYPE: Final = "application/vnd.orcid+json"
ORCID_ID: Final = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
# The sections of a record kept whole when chosen; affiliations, works and fundings are chosen
# item by item, by put-code.
SECTIONS: Final = (
    "researcher_name",
    "other_names",
    "biography",
    "keywords",
    "country",
    "researcher_links",
    "external_identifiers",
)
ITEMISED: Final = ("affiliations", "works", "fundings")
# Each kind of affiliation, with ORCID's group and summary keys.
_AFFILIATIONS: Final = {
    AffiliationKind.EMPLOYMENT: ("employments", "employment-summary"),
    AffiliationKind.EDUCATION: ("educations", "education-summary"),
    AffiliationKind.QUALIFICATION: ("qualifications", "qualification-summary"),
    AffiliationKind.INVITED_POSITION: ("invited-positions", "invited-position-summary"),
    AffiliationKind.DISTINCTION: ("distinctions", "distinction-summary"),
    AffiliationKind.MEMBERSHIP: ("memberships", "membership-summary"),
    AffiliationKind.SERVICE: ("services", "service-summary"),
}


class OrcidError(ValueError):
    """The iD or the choice is not one that can be read or kept."""


class OrcidUnavailableError(Exception):
    """ORCID's public record could not be read: the network, ORCID, or an iD it does not know."""


def public_api(issuer: str) -> str:
    """ORCID's public API for `issuer`. Raises `OrcidError` for an issuer that is not ORCID's."""
    try:
        return PUBLIC_APIS[issuer.rstrip("/")]
    except KeyError:
        raise OrcidError(f"{issuer!r} is not an ORCID issuer, so it has no public record") from None


def issuer_of(principal: Principal) -> str:
    """The ORCID issuer that vouched for `principal`, or, for a principal the operator asserted
    (a development server), the one whose iD URL it is. Raises `OrcidError` for a principal that
    is not an ORCID iD."""
    if principal.vouched_by is not None:
        issuer = principal.vouched_by.rstrip("/")
    else:
        issuer = next(
            (i for i in PUBLIC_APIS if principal.principal_id.startswith(i + "/")),
            principal.principal_id,
        )
    public_api(issuer)
    orcid_path(principal.principal_id, issuer)
    return issuer


def orcid_path(principal_id: str, issuer: str) -> str:
    """The bare iD in `principal_id`, the URL `<issuer>/<iD>` a person signed in as. Raises
    `OrcidError` for a principal that is not an ORCID iD of that issuer."""
    prefix = issuer.rstrip("/") + "/"
    path = principal_id.removeprefix(prefix)
    if path == principal_id or not ORCID_ID.fullmatch(path):
        raise OrcidError(f"{principal_id!r} is not an ORCID iD of {issuer}")
    return path


def record_url(principal_id: str, issuer: str) -> str:
    """Where the public record of the person `principal_id` names is read from."""
    return f"{public_api(issuer)}/{orcid_path(principal_id, issuer)}/record"


def fetch_record(
    principal_id: str, issuer: str, *, transport: httpx.BaseTransport | None = None
) -> dict[str, Any]:
    """The public record of the person `principal_id` names, as ORCID's JSON. `transport` lets a
    test stand in for the network (`dd_harness.testing.FakeOrcidRegistry`). Raises `OrcidError`
    for a principal that is not an ORCID iD, and `OrcidUnavailableError` if the record cannot be
    read."""
    url = record_url(principal_id, issuer)
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT_S, transport=transport) as client:
            response = client.get(url, headers={"Accept": ORCID_MEDIA_TYPE})
            response.raise_for_status()
            document = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OrcidUnavailableError(
            f"the ORCID record could not be read: {type(exc).__name__}"
        ) from exc
    if not isinstance(document, dict):
        raise OrcidUnavailableError("the ORCID record is not an object")
    return document


def normalise(
    raw: Mapping[str, Any], *, principal_id: str, retrieved_at: datetime, source: str
) -> dict[str, Any]:
    """ORCID's JSON for one record as a `ResearcherRecord` document: everything it makes public
    but email addresses, the current affiliations and fundings first and the most recent works
    first, at most `WORKS_OFFERED` of them."""
    person = _get(raw, "person")
    activities = _get(raw, "activities-summary")
    works = sorted(_works(activities), key=_recent_year, reverse=True)
    record: dict[str, Any] = {
        "orcid_id": principal_id,
        "researcher_name": _name(_get(person, "name")),
        "other_names": _contents(_items(person, "other-names", "other-name")),
        "biography": _text(_public(_get(person, "biography")), "content"),
        "keywords": _contents(_items(person, "keywords", "keyword")),
        "country": _unique(_value(a, "country") for a in _items(person, "addresses", "address")),
        "researcher_links": [
            link
            for item in _items(person, "researcher-urls", "researcher-url")
            if (link := _link(item))
        ],
        "external_identifiers": [
            ident
            for item in _items(person, "external-identifiers", "external-identifier")
            if (ident := _identifier(item))
        ],
        "affiliations": sorted(_affiliations(activities), key=_current_first),
        "works": works[:WORKS_OFFERED],
        "works_omitted": len(works) - WORKS_OFFERED if len(works) > WORKS_OFFERED else None,
        "fundings": sorted(_fundings(activities), key=_current_first),
        "record_retrieved_at": retrieved_at.isoformat(),
        "record_source": source,
    }
    return checked(record)


def select(record: Mapping[str, Any], keep: Mapping[str, Any]) -> dict[str, Any]:
    """`record`, a `ResearcherRecord` document, with only what `keep` names: `sections`, a list
    of `SECTIONS`, and for each of `ITEMISED` a list of put-codes. The iD, and when and where the
    record was read, are always kept. Raises `OrcidError` for a key, section or put-code that is
    not the record's, so a choice made against an older reading is refused, not half kept."""
    unknown = set(keep) - {"sections", *ITEMISED}
    if unknown:
        raise OrcidError(f"cannot keep {', '.join(sorted(unknown))}")
    sections = _strings(keep.get("sections", []), "sections")
    wrong = set(sections) - set(SECTIONS)
    if wrong:
        raise OrcidError(f"no section {', '.join(sorted(wrong))}")
    chosen: dict[str, Any] = {
        "orcid_id": record["orcid_id"],
        "record_retrieved_at": record["record_retrieved_at"],
        "record_source": record["record_source"],
    }
    for section in sections:
        if record.get(section) in (None, []):
            raise OrcidError(f"the record no longer has {section}")
        chosen[section] = record[section]
    for section in ITEMISED:
        codes = _strings(keep.get(section, []), section)
        held = {item["put_code"]: item for item in record.get(section, [])}
        missing = [code for code in codes if code not in held]
        if missing:
            raise OrcidError(f"the record no longer has {section} {', '.join(missing)}")
        wanted = set(codes)
        items = [item for code, item in held.items() if code in wanted]
        if items:
            chosen[section] = items
    return checked(chosen)


def checked(record: Mapping[str, Any]) -> dict[str, Any]:
    """`record` as a compact `ResearcherRecord` document, with no empty slot. Raises `OrcidError`
    if it is not one."""
    try:
        model = ResearcherRecord.model_validate(dict(record))
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        raise OrcidError(f"not a ResearcherRecord: {exc}") from exc
    compact: dict[str, Any] = _compact(model.model_dump(mode="json", exclude_none=True))
    return compact


# --- Reading ORCID's JSON -------------------------------------------------------------------


def _get(document: Any, key: str) -> Any:
    return document.get(key) if isinstance(document, Mapping) else None


def _public(item: Any) -> Any:
    """`item` unless ORCID marks it anything but public; the public API returns only public
    items, and this keeps it so whatever is asked."""
    visibility = _get(item, "visibility")
    return item if visibility in (None, "public", "PUBLIC") else None


def _items(document: Any, group: str, key: str) -> list[Any]:
    found = _get(_get(document, group), key)
    return [item for item in found if _public(item)] if isinstance(found, list) else []


def _value(document: Any, key: str) -> str | None:
    """The `value` ORCID wraps a field in, stripped; None when absent or blank."""
    return _text(_get(document, key), "value")


def _text(document: Any, key: str) -> str | None:
    value = _get(document, key)
    return value.strip() or None if isinstance(value, str) else None


def _put_code(item: Any) -> str | None:
    code = _get(item, "put-code")
    return str(code) if isinstance(code, int | str) and str(code) else None


def _year(date: Any) -> int | None:
    year = _value(date, "year")
    return int(year) if year and year.isdigit() else None


def _url(value: str | None) -> str | None:
    """A web address only if it is one, so a malformed entry is left out, not kept."""
    return value if value and re.match(r"^https?://\S+$", value) else None


def _unique(values: Iterable[str | None]) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))


def _contents(items: list[Any]) -> list[str]:
    return _unique(_text(item, "content") for item in items)


def _name(name: Any) -> str | None:
    if not _public(name):
        return None
    credit = _value(name, "credit-name")
    if credit:
        return credit
    parts = [_value(name, "given-names"), _value(name, "family-name")]
    return " ".join(p for p in parts if p) or None


def _link(item: Any) -> dict[str, Any] | None:
    url = _url(_value(item, "url"))
    return {"link_title": _text(item, "url-name"), "link_url": url} if url else None


def _identifier(item: Any) -> dict[str, Any] | None:
    kind, value = _text(item, "external-id-type"), _text(item, "external-id-value")
    if not kind or not value:
        return None
    return {
        "identifier_type": kind,
        "identifier_value": value,
        "identifier_url": _url(_value(item, "external-id-url")),
    }


def _organisation(organisation: Any) -> tuple[str | None, str | None, str | None]:
    """An organisation's name, identifier and the identifier's scheme."""
    found = _get(organisation, "disambiguated-organization")
    identifier = _text(found, "disambiguated-organization-identifier")
    scheme = _text(found, "disambiguation-source") if identifier else None
    return _text(organisation, "name"), identifier, scheme


def _summaries(groups: Any, key: str) -> list[Any]:
    """The first public summary of each group: ORCID groups one work or grant from several
    sources, and the first is the one the holder shows."""
    found = []
    for group in groups if isinstance(groups, list) else []:
        summaries = _get(group, key)
        if isinstance(summaries, Mapping):
            summaries = [summaries]
        first = next((s for s in summaries or [] if _public(s)), None)
        if first is not None:
            found.append(first)
    return found


def _affiliations(activities: Any) -> Iterable[dict[str, Any]]:
    for kind, (group, key) in _AFFILIATIONS.items():
        groups = _get(_get(activities, group), "affiliation-group")
        for summary in _summaries(groups, "summaries"):
            item = _get(summary, key)
            code = _put_code(item)
            name, identifier, scheme = _organisation(_get(item, "organization"))
            if not _public(item) or code is None or name is None:
                continue
            yield {
                "put_code": code,
                "affiliation_kind": kind.value,
                "organisation_name": name,
                "organisation_identifier": identifier,
                "organisation_identifier_scheme": scheme,
                "department": _text(item, "department-name"),
                "role_title": _text(item, "role-title"),
                "start_year": _year(_get(item, "start-date")),
                "end_year": _year(_get(item, "end-date")),
            }


def _works(activities: Any) -> Iterable[dict[str, Any]]:
    groups = _get(_get(activities, "works"), "group")
    for item in _summaries(groups, "work-summary"):
        code = _put_code(item)
        title = _value(_get(item, "title"), "title")
        if code is None or title is None:
            continue
        yield {
            "put_code": code,
            "work_title": title,
            "work_type": _text(item, "type"),
            "publication_year": _year(_get(item, "publication-date")),
            "journal_title": _value(item, "journal-title"),
            "work_identifiers": [
                ident
                for e in _items(item, "external-ids", "external-id")
                if _get(e, "external-id-relationship") in (None, "self", "SELF")
                and (ident := _identifier(e))
            ],
        }


def _fundings(activities: Any) -> Iterable[dict[str, Any]]:
    groups = _get(_get(activities, "fundings"), "group")
    for item in _summaries(groups, "funding-summary"):
        code = _put_code(item)
        title = _value(_get(item, "title"), "title")
        funder, identifier, scheme = _organisation(_get(item, "organization"))
        if code is None or title is None or funder is None:
            continue
        award = next(
            (
                _text(e, "external-id-value")
                for e in _items(item, "external-ids", "external-id")
                if _text(e, "external-id-type") in ("grant_number", "GRANT_NUMBER")
            ),
            None,
        )
        yield {
            "put_code": code,
            "funding_title": title,
            "funding_type": _text(item, "type"),
            "funder_name": funder,
            "funder_identifier": identifier,
            "funder_identifier_scheme": scheme,
            "award_identifier": award,
            "start_year": _year(_get(item, "start-date")),
            "end_year": _year(_get(item, "end-date")),
        }


def _current_first(item: Mapping[str, Any]) -> tuple[bool, int]:
    """Ongoing items first, then the most recently started."""
    return item.get("end_year") is not None, -(item.get("start_year") or 0)


def _recent_year(item: Mapping[str, Any]) -> int:
    return int(item.get("publication_year") or 0)


def _strings(value: Any, section: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise OrcidError(f"{section} is a list of names or put-codes")
    return list(value)


def _compact(document: Any) -> Any:
    """`document` with every empty list and every slot whose value is None or empty removed."""
    if isinstance(document, dict):
        return {
            key: _compact(value)
            for key, value in document.items()
            if value is not None and value != []
        }
    if isinstance(document, list):
        return [_compact(item) for item in document]
    return document

"""ROR's records as the policy advisor keeps them (`ror.py`): an organisation cut to what
identifying it needs, mapped from a ROR v2 record as the dump and the API both give it, and how a
name or an identifier is matched against it.

Like `ror.py`, this module does not use the Data Director contract (docs/specs/system.md).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

ROR_URL = "https://ror.org/"

# A bare ROR identifier: a zero, six characters and two check digits.
ROR_ID = re.compile(r"^(?:https?://ror\.org/)?(0[a-z0-9]{6}[0-9]{2})/?$")
ACTIVE = "active"
FUNDER = "funder"


def ror_url(value: str) -> str | None:
    """`value` as a ROR identifier URL (`https://ror.org/0xxxxxxNN`), or None if it is not one."""
    found = ROR_ID.match(value.strip().lower())
    return f"{ROR_URL}{found.group(1)}" if found else None


def normalise(name: str) -> str:
    """A name as it is matched: case-folded, with runs of spaces made one."""
    return " ".join(name.casefold().split())


class Name(BaseModel):
    """One of an organisation's names, with ROR's types for it (label, acronym, alias,
    ror_display) and its language, where ROR gives one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str
    types: list[str] = Field(default_factory=list)
    lang: str | None = None

    @field_validator("types")
    @classmethod
    def _sort(cls, values: list[str]) -> list[str]:
        return sorted(set(values))


class Organisation(BaseModel):
    """An organisation as ROR records it, cut to what identifying it needs. Stored in the
    registry exactly as it is hashed, so the line is the document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    """The ROR identifier, as a URL: what the payload cites."""
    names: list[Name]
    types: list[str] = Field(default_factory=list)
    status: str
    country_codes: list[str] = Field(default_factory=list)
    # Crossref Funder IDs (ROR's `fundref`), and the one ROR prefers, where it names one.
    crossref_funder_ids: list[str] = Field(default_factory=list)
    crossref_funder_preferred: str | None = None
    # The organisations ROR names as this one's parents, by identifier.
    parents: list[str] = Field(default_factory=list)

    @field_validator("types", "country_codes", "crossref_funder_ids", "parents")
    @classmethod
    def _sort(cls, values: list[str]) -> list[str]:
        return sorted(set(values))

    @field_validator("names")
    @classmethod
    def _sort_names(cls, values: list[Name]) -> list[Name]:
        unique = {(n.value, tuple(n.types), n.lang or ""): n for n in values}
        return [unique[k] for k in sorted(unique)]

    def document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @property
    def label(self) -> str:
        """The name ROR displays."""
        for wanted in ("ror_display", "label"):
            for name in self.names:
                if wanted in name.types:
                    return name.value
        return self.names[0].value if self.names else self.id

    def all_names(self) -> list[str]:
        """Every name, display name first, then labels, acronyms and aliases, each once."""
        order = {"ror_display": 0, "label": 1, "acronym": 2, "alias": 3}
        ranked = sorted(
            self.names, key=lambda n: (min((order.get(t, 4) for t in n.types), default=4), n.value)
        )
        out: list[str] = []
        for name in ranked:
            if name.value not in out:
                out.append(name.value)
        return out

    def matches(self, name: str) -> bool:
        wanted = normalise(name)
        return any(normalise(n.value) == wanted for n in self.names)

    @property
    def active(self) -> bool:
        return self.status == ACTIVE


def from_ror_json(item: dict[str, Any]) -> Organisation:
    """An organisation from a ROR v2 record, as the dump and the API both give it."""
    fundref: dict[str, Any] = next(
        (e for e in item.get("external_ids") or [] if e.get("type") == "fundref"), {}
    )
    return Organisation(
        id=item["id"],
        names=[
            Name(value=n["value"], types=n.get("types") or [], lang=n.get("lang"))
            for n in item.get("names") or []
            if n.get("value")
        ],
        types=item.get("types") or [],
        status=item.get("status") or "",
        country_codes=[
            code
            for loc in item.get("locations") or []
            if (code := (loc.get("geonames_details") or {}).get("country_code"))
        ],
        crossref_funder_ids=[str(v) for v in fundref.get("all") or []],
        crossref_funder_preferred=fundref.get("preferred"),
        parents=[r["id"] for r in item.get("relationships") or [] if r.get("type") == "parent"],
    )

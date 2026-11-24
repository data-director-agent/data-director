"""How the librarian drafts in one standard: each property's form, from the standard's definition
(docs/specs/metadata-standards.md), and the shared field each pivot term gives (`shares.yaml`).

A property's form is its value key, from the definition's properties, and the definition's
drafting advice for it: what is asked about a gap, what a person must decide may be published
before it is asked, whether a model may suggest a value, and a value filled by rule. That advice
is a ceiling, not a licence: the rules of docs/specs/drafting.md still apply.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from dd_agent_advisor_metadata.questions import Gap
from dd_metadata_records import Definition, Standard, expand
from dd_sdk.contract.questions import SharedField

# Which shared field the first entry under each pivot term gives (docs/specs/drafting.md,
# invariant 11). It is Data Director's contract, not a standard's, so it is kept here.
SHARES = Path(__file__).with_name("shares.yaml")
# A list entry after the first, anywhere in a gap's path.
_LATER_ENTRY = re.compile(r"\[[1-9][0-9]*\]")


@dataclass(frozen=True, slots=True)
class Form:
    """How one property is written: the key of its value in a list entry, or a value the
    librarian fills itself; the question asked about a value left as a gap, the question asked
    first about whether it may be published at all, and whether a model may suggest one."""

    value: str | None = None
    filled: str | None = None
    ask: str | None = None
    publish: str | None = None
    suggest: bool = False


@dataclass(frozen=True)
class Drafting:
    """What the librarian needs of a standard to draft in it."""

    standard: Standard
    form: Mapping[str, Form]
    shares: Mapping[str, SharedField]

    @property
    def definition(self) -> Definition:
        return self.standard.definition

    @property
    def media_type(self) -> str:
        """The serialisation the record is written in: the definition's first."""
        return self.definition.serialisations[0].media_type

    def form_of(self, prop: str) -> Form:
        return self.form.get(prop, Form())

    def path_for(self, term: str) -> str | None:
        """The path of the property the definition reads under `term`, an IRI, if it has one."""
        found = self.definition.property_for(term)
        return found.path if found else None

    def shared_field(self, gap: Gap) -> SharedField | None:
        """The shared field `gap` asks for: only in the property's first entry, since the
        researcher gave one answer for the dataset as a whole."""
        if "[0]" not in gap.path or _LATER_ENTRY.search(gap.path):
            return None
        term = self.definition.term(gap.prop, gap.qualifier)
        return self.shares.get(term) if term else None


def load_form(definition: Definition) -> dict[str, Form]:
    """The form of each property of `definition`. Raises `ValueError` for advice that both fills
    a value by rule and names a key for it."""
    form = {}
    for path, prop in definition.properties.items():
        advice: Mapping[str, Any] = definition.drafting.get(path, {})
        if prop.value is not None and "filled" in advice:
            raise ValueError(f"{definition.ref}: {path} has a value key and a filled value")
        form[path] = Form(value=prop.value, **advice)
    return form


def load_shares(path: Path = SHARES) -> dict[str, SharedField]:
    """The shared field each pivot term gives, by the term's IRI."""
    with path.open(encoding="utf-8") as fh:
        table: dict[str, str] = yaml.safe_load(fh) or {}
    return {expand(term): SharedField(field) for term, field in table.items()}


@cache
def _shares() -> dict[str, SharedField]:
    return load_shares()


def drafting(standard: Standard) -> Drafting:
    """How to draft in `standard`."""
    return Drafting(standard, load_form(standard.definition), _shares())

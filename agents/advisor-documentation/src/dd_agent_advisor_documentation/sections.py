"""A sectioned document's sections (docs/specs/drafting.md): the README's (`readme.yaml`) and the
Data Management Plan's (`plan.py`). What each asks, the project facts it is drafted from, its
parts, whether a model may suggest an answer to it, and the shared field it asks for, if any."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, NamedTuple

import yaml

from dd_sdk.contract.questions import SharedField

README = Path(__file__).with_name("readme.yaml")
# The project facts a section may be drafted from (readme.yaml explains each; `drafted.py` the
# decided facts a Data Management Plan also draws on: funders, repository, licence, sensitivity
# and the data description, in full or so far).
SOURCES = frozenset(
    {
        "files",
        "licences",
        "record_general",
        "record_abstract",
        "record_rights",
        "record_citation",
        "standards",
        "funders",
        "repository",
        "licence",
        "sensitivity",
        "data_description",
        "data_description_so_far",
        "project",
    }
)
# A section's `suggest` value for "only from the documents the researcher attached".
FROM_DOCUMENTS = "documents"
# The approved metadata record's general values a README part may be given by (readme.yaml), and
# the label each is drafted under.
RECORD_GENERAL = {
    "title": "Title",
    "creators": "Creators",
    "collected": "Dates of data collection",
    "location": "Geographic location",
    "funding": "Funding",
}


class Part(NamedTuple):
    """One thing a section asks, asked as a question of its own and placed under its label."""

    label: str
    ask: str
    # The record's general value that, when the record gives it, says all the part asks.
    given_by: str | None = None
    # The value it asks for that every kind of document gives the same way (`SharedField`).
    shares: SharedField | None = None


class Section(NamedTuple):
    heading: str
    # What the section asks as one question; for a section with parts, all of them in one line.
    ask: str
    # The project facts it is drafted from, in order; empty: the researcher writes it all.
    sources: tuple[str, ...] = ()
    # The fact that, when it gives anything, says all the section asks, so no gap is left.
    complete_from: str | None = None
    # What it asks, part by part; empty: it asks `ask` as one question.
    parts: tuple[Part, ...] = ()
    # Whether a model may suggest an answer to its question, offered beside it: always (True),
    # or only from the documents the researcher attached (FROM_DOCUMENTS).
    suggest: bool | Literal["documents"] = False
    # The value its question asks for that every kind of document gives the same way.
    shares: SharedField | None = None
    # What it asks before the data are collected, when it asks something else then (readme.yaml).
    plan_ask: str | None = None

    def suggestable(self, *, has_documents: bool) -> bool:
        """Whether a model may suggest an answer to this section's question, in a draft that
        carries attached documents or not."""
        return self.suggest is True or (self.suggest == FROM_DOCUMENTS and has_documents)


def load_sections(path: Path = README) -> list[Section]:
    with path.open(encoding="utf-8") as fh:
        table = yaml.safe_load(fh)
    return sections_from(table, path)


def sections_from(table: Sequence[Mapping[str, Any]], path: Path | str) -> list[Section]:
    """The sections a table of entries describes, in the form of `readme.yaml`; `path` names
    where the table came from, for its errors."""
    sections = []
    for entry in table:
        given = entry.get("from")
        sources = (given,) if isinstance(given, str) else tuple(given or ())
        complete_from = entry.get("complete_from")
        for source in sources:
            if source not in SOURCES:
                raise ValueError(
                    f"{path}: section {entry['heading']!r} drafts from unknown {source!r}"
                )
        if complete_from is not None and complete_from not in sources:
            raise ValueError(
                f"{path}: section {entry['heading']!r} is completed from {complete_from!r}, "
                "which it is not drafted from"
            )
        parts = tuple(_part(path, entry["heading"], p) for p in entry.get("parts") or ())
        if ("ask" in entry) == bool(parts):
            raise ValueError(f"{path}: section {entry['heading']!r} needs either ask or parts")
        if parts and complete_from is not None:
            raise ValueError(
                f"{path}: section {entry['heading']!r} has parts, so it cannot be completed "
                "from one fact"
            )
        suggest = entry.get("suggest", False)
        if not isinstance(suggest, bool) and suggest != FROM_DOCUMENTS:
            raise ValueError(
                f"{path}: section {entry['heading']!r} has a suggest that is not true, false or "
                f"{FROM_DOCUMENTS}"
            )
        if parts and suggest:
            raise ValueError(
                f"{path}: section {entry['heading']!r} has parts, which a model does not suggest"
            )
        ask = (
            " ".join(str(entry["ask"]).split())
            if not parts
            else "; ".join(f"{p.label.lower()}: {p.ask.rstrip('.')}" for p in parts) + "."
        )
        sections.append(
            Section(
                str(entry["heading"]),
                ask,
                sources,
                complete_from,
                parts,
                suggest,
                _shares(path, entry["heading"], entry),
                _plan_ask(path, entry["heading"], entry, parts),
            )
        )
    if not sections:
        raise ValueError(f"{path}: no sections")
    return sections


def _plan_ask(
    path: Path | str, heading: str, entry: Mapping[str, Any], parts: tuple[Part, ...]
) -> str | None:
    plan_ask = entry.get("plan_ask")
    if plan_ask is None:
        return None
    if parts:
        raise ValueError(f"{path}: section {heading!r} has parts, so it has no plan_ask")
    return " ".join(str(plan_ask).split())


def before_collection(sections: Sequence[Section]) -> list[Section]:
    """The sections as asked before the data are collected: each with a `plan_ask` asks it in
    place of its `ask`, under the same question (#1017)."""
    return [s._replace(ask=s.plan_ask) if s.plan_ask else s for s in sections]


def _part(path: Path | str, heading: str, entry: Mapping[str, Any]) -> Part:
    given_by = entry.get("given_by")
    if given_by is not None and given_by not in RECORD_GENERAL:
        raise ValueError(f"{path}: section {heading!r} has a part given by unknown {given_by!r}")
    return Part(
        str(entry["label"]),
        " ".join(str(entry["ask"]).split()),
        given_by,
        _shares(path, heading, entry),
    )


def _shares(path: Path | str, heading: str, entry: Mapping[str, Any]) -> SharedField | None:
    shares = entry.get("shares")
    if shares is None:
        return None
    try:
        return SharedField(shares)
    except ValueError:
        raise ValueError(f"{path}: section {heading!r} shares unknown {shares!r}") from None

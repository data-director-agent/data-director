"""The schemes, read from the JSON files beside this module (`data/<id>.json`)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Final

SCHEMES: Final = ("oecd-fos", "anzsrc-for")


@dataclass(frozen=True)
class Term:
    """One field of a scheme: its code, its label as published, and the code of the field it is
    under (None for a top-level field)."""

    code: str
    label: str
    parent: str | None


@dataclass(frozen=True)
class Scheme:
    """A classification, with where it comes from and on what terms it may be reused."""

    id: str
    name: str
    version: str
    source: str
    licence: str
    attribution: str
    terms: tuple[Term, ...]


@cache
def scheme(scheme_id: str) -> Scheme:
    """The scheme named `scheme_id`, one of `SCHEMES`. Raises KeyError for any other name."""
    if scheme_id not in SCHEMES:
        raise KeyError(f"no subject scheme {scheme_id!r}; the schemes are {', '.join(SCHEMES)}")
    data = json.loads(
        resources.files("dd_subjects").joinpath("data", f"{scheme_id}.json").read_text("utf-8")
    )
    terms = tuple(Term(t["code"], t["label"], t["parent"]) for t in data.pop("terms"))
    return Scheme(terms=terms, **data)


def suggestions(scheme_id: str) -> list[str]:
    """The scheme's labels in code order, each broad field before the fields under it, without
    repeats."""
    return list(dict.fromkeys(t.label for t in scheme(scheme_id).terms))

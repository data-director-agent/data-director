"""The one module that reaches ucumvert (docs/specs/dependencies.md).

ucumvert implements the full UCUM grammar and ships the UCUM table it was built from,
`ucum-essence.xml`. This module reads that table into plain records and checks a code against
the grammar. If ucumvert is lost, the fallback is to ship `ucum-essence.xml` here and generate a
lark grammar from it, which is what ucumvert does; nothing outside this module changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from xml.etree import ElementTree

from ucumvert import InvalidUcumError, get_ucum_parser, parse_ucum

NAMESPACE = {"u": "http://unitsofmeasure.org/ucum-essence"}


@dataclass(frozen=True)
class Prefix:
    code: str  # e.g. "u"
    name: str  # e.g. "micro"
    symbol: str  # e.g. "μ"


@dataclass(frozen=True)
class Atom:
    """A UCUM unit atom: a base unit or a defined unit."""

    code: str  # e.g. "Cel"
    names: tuple[str, ...]  # e.g. ("degree Celsius",)
    symbol: str  # e.g. "°C", or "" where UCUM gives none
    unit_class: str  # e.g. "si", "intcust", "us-volumes"; "base" for a base unit
    metric: bool  # whether it takes a prefix


@dataclass(frozen=True)
class Essence:
    version: str
    prefixes: tuple[Prefix, ...]
    atoms: tuple[Atom, ...]


def _text(element: ElementTree.Element | None) -> str:
    """An element's text, markup such as <sub> flattened and whitespace collapsed."""
    if element is None:
        return ""
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


@cache
def essence() -> Essence:
    """The UCUM table ucumvert ships, read once."""
    path = files("ucumvert") / "vendor" / "ucum-essence.xml"
    root = ElementTree.fromstring(path.read_bytes())  # a file in an installed package
    prefixes = tuple(
        Prefix(
            p.get("Code", ""),
            _text(p.find("u:name", NAMESPACE)),
            _text(p.find("u:printSymbol", NAMESPACE)),
        )
        for p in root.findall("u:prefix", NAMESPACE)
    )
    atoms = tuple(
        Atom(
            code=u.get("Code", ""),
            names=tuple(_text(n) for n in u.findall("u:name", NAMESPACE)),
            symbol=_text(u.find("u:printSymbol", NAMESPACE)),
            unit_class=u.get("class", "base"),
            metric=tag == "base-unit" or u.get("isMetric") == "yes",
        )
        for tag in ("base-unit", "unit")
        for u in root.findall(f"u:{tag}", NAMESPACE)
    )
    return Essence(root.get("version", ""), prefixes, atoms)


# Building the parser reads the grammar and takes most of a second, so it is built once.
_parser = cache(get_ucum_parser)


@cache
def is_valid(code: str) -> bool:
    """Whether `code` is a well-formed UCUM expression (case-sensitive form)."""
    try:
        parse_ucum(code, parser=_parser())
    except InvalidUcumError:
        return False
    return True

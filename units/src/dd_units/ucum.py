"""Turn a unit as a person writes it into a UCUM code, by rule.

The rule never guesses. A unit is matched, in order:

1. as a whole phrase: a UCUM unit name ("degree Celsius"), a print symbol ("°C") or one of a few
   common spellings UCUM does not list ("degC", "micron");
2. term by term, split at "/", "per", "." and spaces, each term a unit atom with an optional
   prefix and exponent, found by its UCUM code, name or print symbol ("mg per litre",
   "micrometres", "m²", "kg m-3", "square metres", and the micro sign for micro-);
3. as a UCUM expression written as it stands ("10*3/uL").

Every code it returns is checked against the UCUM grammar. Where UCUM gives one name or symbol
to several units, the one in the most general class wins (SI and ISO 1000 before the
international customary units, and those before the US, British and other national ones); where
two remain, as for a pint or a gallon, the name matches nothing. A few codes whose everyday
reading differs from UCUM's (`C` is the coulomb, not a degree Celsius) are never matched as
written, so that a person is asked instead.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import cache
from typing import Literal

from dd_units import _ucum
from dd_units._ucum import Atom, Prefix

# Codes that are valid UCUM but whose everyday reading is another unit. Written as they stand,
# they match nothing; with a prefix (`mC`) they mean what UCUM says.
AMBIGUOUS = {
    "C": "the coulomb in UCUM, often written for a degree Celsius",
    "F": "the farad in UCUM, often written for a degree Fahrenheit",
    "G": "the gauss in UCUM, often written for a gram or for giga-",
    "B": "the bel in UCUM, often written for a byte",
    "b": "the barn in UCUM, often written for a bit",
    "deg": "the plane-angle degree in UCUM, often written for a temperature",
}

# Common spellings UCUM lists neither as a name nor as a print symbol, matched case-insensitively.
ALIASES = {
    **dict.fromkeys(
        ("degc", "deg c", "deg. c", "° c", "celsius", "centigrade", "degree c", "degrees c"),
        "Cel",
    ),
    **dict.fromkeys(
        ("degf", "deg f", "deg. f", "° f", "fahrenheit", "degree f", "degrees f"), "[degF]"
    ),
    **dict.fromkeys(("micron", "microns"), "um"),
    **dict.fromkeys(("hr", "hrs"), "h"),
    **dict.fromkeys(("sec", "secs"), "s"),
    "mins": "min",
    **dict.fromkeys(("yr", "yrs"), "a"),
    **dict.fromkeys(("percent", "per cent", "pct"), "%"),
    **dict.fromkeys(("ha", "hectare", "hectares"), "har"),
}

# What a person writes for a field that has no unit.
NO_UNIT = {
    "none",
    "no unit",
    "no units",
    "n/a",
    "na",
    "not applicable",
    "-",
    "\u2013",  # en dash
    "\u2014",  # em dash
    "dimensionless",
    "unitless",
}

# Which units' names and symbols win where UCUM gives the same one to several: lower first.
CLASS_RANK = {"base": 0, "si": 1, "iso1000": 2, "intcust": 3, "avoirdupois": 4, "dimless": 5}
OTHER_CLASS = 9
# Atoms never matched by name or symbol: UCUM's alternatives for the minute and second (' and ''),
# its "ten" for powers, and the lower-case litre where the upper-case one is clearer.
NOT_BY_NAME = {"'", "''", "10*", "10^", "l"}
# Names UCUM gives one unit but people use for another: "gallon" is the British gallon in UCUM,
# and the US gallon is named differently, so a gallon could be either.
UNCLEAR_NAMES = {"gallon"}
# Names for prefixed atoms that are written as one word, not as prefix and atom.
COMPOUND_NAMES = {"har": "hectare"}
# How UCUM's American names are written in British English, for the names this returns.
BRITISH = (("meter", "metre"), ("liter", "litre"), ("deka", "deca"))
SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
MICRO_SIGN, GREEK_MU = "\u00b5", "\u03bc"
EXPONENT = re.compile(r"^(?P<base>\D.*?)(?P<exponent>-?\d+)$")
WORD_POWERS = (
    ("square ", "", "2"),
    ("cubic ", "", "3"),
    ("", " squared", "2"),
    ("", " cubed", "3"),
)


@dataclass(frozen=True)
class UcumUnit:
    """A UCUM code for a unit a person wrote, with how it was found."""

    code: str  # e.g. "um", "Cel", "mg/L"
    name: str | None  # UCUM's name in British spelling, e.g. "micrometre"; None if not composed
    matched_by: Literal["code", "name"]  # "code" when the text was already this UCUM code


class _AmbiguousError(Exception):
    """A term is one of the AMBIGUOUS codes: the whole unit matches nothing."""


@dataclass(frozen=True)
class _Term:
    code: str
    name: str


@dataclass(frozen=True)
class _Tables:
    by_code: dict[str, Atom]
    by_name: dict[str, Atom]
    by_symbol: dict[str, Atom]
    prefixes: tuple[Prefix, ...]  # longest code first, so "da" is tried before "d"


def ucum_version() -> str:
    """The version of the UCUM table the rule reads."""
    return _ucum.essence().version


def means_no_unit(text: str) -> bool:
    """Whether a person wrote that a field has no unit."""
    return text.strip().rstrip(".").casefold() in NO_UNIT


def ucum_code(text: str) -> UcumUnit | None:
    """The UCUM code for a unit written by a person, or None if the rule cannot tell."""
    written = " ".join(text.split())
    if not written or written in AMBIGUOUS or means_no_unit(written):
        return None
    try:
        whole = _phrase(written)
        if whole is not None:
            return _unit(whole, written)
        composed = _compose(_normalise(written))
    except _AmbiguousError:
        return None
    if composed is not None and _ucum.is_valid(composed.code):
        return _unit(composed, written)
    if _ucum.is_valid(written):
        return UcumUnit(written, None, "code")
    return None


def _unit(term: _Term, written: str) -> UcumUnit:
    return UcumUnit(term.code, term.name, "code" if term.code == written else "name")


def _normalise(text: str) -> str:
    """Superscripts as digits, the micro sign as mu, and products written with a dot."""
    text = text.translate(SUPERSCRIPTS).replace(MICRO_SIGN, GREEK_MU)
    text = text.replace("**", "").replace("^", "")
    return re.sub("\\s*[\u00b7\u22c5\u00d7*]\\s*", ".", text)


def _compose(text: str) -> _Term | None:
    """A unit made of terms: a numerator, then each part after "/" or "per" divides it."""
    parts = re.split(r"\s+per\s+|/", text, flags=re.IGNORECASE)
    numerator = _terms(parts[0]) if parts[0].strip() else []
    denominators = [_terms(p) for p in parts[1:]]
    if numerator is None or any(d is None for d in denominators) or not (numerator or parts[1:]):
        return None
    below = [t for d in denominators if d is not None for t in d]
    code = ".".join(t.code for t in numerator) + "".join(f"/{t.code}" for t in below)
    name = " ".join(t.name for t in numerator) + "".join(f" per {t.name}" for t in below)
    return _Term(code, name.strip())


def _terms(part: str) -> list[_Term] | None:
    """The terms of a product, taking the longest run of words that names a unit first, so that
    "degree Celsius" is one term and "kg m-3" two."""
    words = [w for w in re.split(r"[.\s]+", part.strip()) if w]
    found: list[_Term] = []
    start = 0
    while start < len(words):
        for end in range(len(words), start, -1):
            term = _term(" ".join(words[start:end]))
            if term is not None:
                found.append(term)
                start = end
                break
        else:
            return None
    return found or None


def _term(phrase: str) -> _Term | None:
    """One term: a unit atom, perhaps prefixed, perhaps raised to a power."""
    for base, exponent in _powers(phrase):
        atom = _atom(base)
        if atom is not None:
            if not exponent:
                return atom
            return _Term(f"{atom.code}{exponent}", f"{atom.name}^{exponent}")
    return None


def _powers(phrase: str) -> Iterator[tuple[str, str]]:
    """Ways of reading a phrase as a base and an exponent, the plainest first."""
    yield phrase, ""
    folded = phrase.casefold()
    for before, after, exponent in WORD_POWERS:
        if (
            folded.startswith(before)
            and folded.endswith(after)
            and len(folded) > len(before + after)
        ):
            yield phrase[len(before) : len(phrase) - len(after)], exponent
    if " " not in phrase and (match := EXPONENT.match(phrase)):
        yield match["base"], match["exponent"]


def _phrase(text: str) -> _Term | None:
    """A whole phrase that names one unit: a common spelling, a name or a print symbol."""
    alias = ALIASES.get(text.casefold())
    if alias is not None:
        return _atom(alias)
    tables = _tables()
    atom = _by_name(tables, text) or tables.by_symbol.get(text.replace(MICRO_SIGN, GREEK_MU))
    return _named(atom) if atom is not None else None


def _atom(base: str) -> _Term | None:
    """A unit atom, by its code, a common spelling, its name or its print symbol, or a metric atom
    after a prefix written the same way. Raises _AmbiguousError for a code in AMBIGUOUS."""
    if base in AMBIGUOUS:
        raise _AmbiguousError(base)
    tables = _tables()
    alias = ALIASES.get(base.casefold())
    if alias is not None and alias != base:
        return _atom(alias)
    atom = (
        tables.by_code.get(base)
        or _by_name(tables, base)
        or tables.by_symbol.get(base.replace(MICRO_SIGN, GREEK_MU))
    )
    if atom is not None:
        return _named(atom)
    return _prefixed(tables, base)


def _prefixed(tables: _Tables, base: str) -> _Term | None:
    """A metric atom after a prefix: by code or symbol after a prefix's code or symbol ("mg",
    "μm"), or by name after a prefix's name ("micrometre")."""
    folded = base.casefold()
    for prefix in tables.prefixes:
        for start in {prefix.code, prefix.symbol}:
            rest = base[len(start) :] if base.startswith(start) else ""
            atom = tables.by_code.get(rest) or tables.by_symbol.get(rest)
            if rest and rest not in AMBIGUOUS and atom is not None and atom.metric:
                return _with_prefix(prefix, atom)
        if folded.startswith(prefix.name) and len(folded) > len(prefix.name):
            atom = _by_name(tables, base[len(prefix.name) :])
            if atom is not None and atom.metric:
                return _with_prefix(prefix, atom)
    return None


def _with_prefix(prefix: Prefix, atom: Atom) -> _Term:
    code = prefix.code + atom.code
    return _Term(code, COMPOUND_NAMES.get(code) or _british(prefix.name + _name(atom)))


def _by_name(tables: _Tables, text: str) -> Atom | None:
    for spelling in _spellings(text):
        atom = tables.by_name.get(spelling)
        if atom is not None:
            return atom
    return None


def _spellings(text: str) -> Iterator[str]:
    """A name as written, in American spelling, and with each word made singular."""
    folded = text.casefold()
    for american, british in BRITISH:
        folded = folded.replace(british, american)
    yield folded
    singular = " ".join(_singular(w) for w in folded.split())
    if singular != folded:
        yield singular


def _singular(word: str) -> str:
    if word == "feet":
        return "foot"
    if word.endswith(("ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us")) and len(word) > 3:
        return word[:-1]
    return word


def _named(atom: Atom) -> _Term:
    return _Term(atom.code, _british(_name(atom)))


def _name(atom: Atom) -> str:
    return atom.names[0] if atom.names else atom.code


def _british(name: str) -> str:
    for american, british in BRITISH:
        name = name.replace(american, british)
    return name


@cache
def _tables() -> _Tables:
    essence = _ucum.essence()
    lookup = [a for a in essence.atoms if a.code not in NOT_BY_NAME]
    return _Tables(
        by_code={a.code: a for a in essence.atoms},
        by_name=_preferred(
            (n.casefold(), a) for a in lookup for n in a.names if n.casefold() not in UNCLEAR_NAMES
        ),
        by_symbol=_preferred((a.symbol, a) for a in lookup if a.symbol),
        prefixes=tuple(sorted(essence.prefixes, key=lambda p: -len(p.code))),
    )


def _preferred(pairs: Iterable[tuple[str, Atom]]) -> dict[str, Atom]:
    """Each key's atom of the most general class, leaving out a key that two such atoms share."""
    candidates: defaultdict[str, set[Atom]] = defaultdict(set)
    for key, atom in pairs:
        candidates[key].add(atom)
    preferred = {}
    for key, atoms in candidates.items():
        best = min(CLASS_RANK.get(a.unit_class, OTHER_CLASS) for a in atoms)
        top = [a for a in atoms if CLASS_RANK.get(a.unit_class, OTHER_CLASS) == best]
        if len(top) == 1:
            preferred[key] = top[0]
    return preferred

"""The DFG subject classification, under which re3data files every repository.

re3data records a repository's subjects from the DFG's classification, with each subject's code
before its name (`34601 Hydrogeology, Hydrology, ...`) and, almost always, every subject above
it too (`3`, `34`, `346`). The classification has four levels, and a code's parents are its
prefixes: `34601` (a subject) is under `346` (a subject area), under `34` (a review board),
under `3` (Natural Sciences).

A theme is matched to the subjects it names, using the subject names that occur in the registry,
so that a repository can be judged by where re3data files it as well as by the words in its
record. Matching is by words, deterministic, and makes no guess: a theme that names no subject
is judged on its text alone.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

_CODED = re.compile(r"^(\d+)\s+(.+)$")
# A subject name lists several fields ("Hydrogeology, Hydrology, Limnology"): a theme must name
# one of them, not take words from several.
_SEGMENT = re.compile(r"[,;]|\band\b|\bas well as\b", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(["of", "the", "in", "for", "on", "with", "including", "und"])
# The level of a code by its length: the top level is a single digit; a subject has five.
_LEVELS = {1: 1, 2: 2, 3: 3, 5: 4}


def parse(subject: str) -> tuple[str, str] | None:
    """`34 Geosciences` as `("34", "Geosciences")`; None for a subject with no DFG code."""
    found = _CODED.match(subject.strip())
    if found is None or len(found.group(1)) not in _LEVELS:
        return None
    return found.group(1), found.group(2).strip()


def codes(subjects: Iterable[str]) -> set[str]:
    return {p[0] for s in subjects if (p := parse(s)) is not None}


def level(code: str) -> int:
    return _LEVELS[len(code)]


def ancestors(code: str) -> list[str]:
    """The subjects above `code`, nearest first: `34601` gives `346`, `34`, `3`."""
    return [code[:n] for n in (3, 2, 1) if n < len(code)]


def vocabulary(subjects: Iterable[str]) -> dict[str, str]:
    """Each DFG code that occurs, with its name."""
    out: dict[str, str] = {}
    for s in subjects:
        if (p := parse(s)) is not None:
            out.setdefault(*p)
    return dict(sorted(out.items()))


def _words(text: str) -> frozenset[str]:
    """Words, with a plural's final "s" dropped, so "soil science" names "Soil Sciences". Not
    from "-ics", so "economics" does not name "Economic and Social History"."""
    out = set()
    for w in _WORD.findall(text.lower()):
        if w in _STOP:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "ics")):
            w = w[:-1]
        out.add(w)
    return frozenset(out)


def resolve(theme: str, names: dict[str, str]) -> list[str]:
    """The codes of the subjects a theme names: those with a field that contains every word of
    the theme, keeping only the closest, where the theme is the largest share of the field's
    words. "medicine" names `22 Medicine` and `222 Medicine`, not `23101 Veterinary Medicine`;
    "fluid dynamics" names nothing, though one subject lists "Nonlinear Dynamics" and "Soft and
    Fluid Matter". Sorted; empty when the theme names no subject."""
    wanted = _words(theme)
    if not wanted:
        return []
    best = 0.0
    found: list[str] = []
    for code, name in names.items():
        for segment in _SEGMENT.split(name):
            words = _words(segment)
            if not wanted <= words:
                continue
            share = len(wanted) / len(words)
            if share > best:
                best, found = share, [code]
            elif share == best and code not in found:
                found.append(code)
    return sorted(found)


@dataclass(frozen=True)
class SubjectMatch:
    """How near a repository is filed to a subject a theme names."""

    target: str  # the code the theme names
    listed: str  # the code the repository lists: the target, or one above it
    steps: int  # how many levels above the target `listed` is; 0 for the target itself


def nearest(targets: Iterable[str], listed: set[str]) -> SubjectMatch | None:
    """The repository's subject nearest to any of the targets: the target itself (or one below
    it), else the closest subject above it. The top level ("Natural Sciences") never counts, as
    a third of re3data is filed under each. None when nothing is near."""
    best: SubjectMatch | None = None
    for target in targets:
        if target in listed or any(c.startswith(target) for c in listed):
            return SubjectMatch(target, target, 0)
        for steps, above in enumerate(ancestors(target), start=1):
            if level(above) == 1:
                break
            if above in listed:
                if best is None or steps < best.steps:
                    best = SubjectMatch(target, above, steps)
                break
    return best

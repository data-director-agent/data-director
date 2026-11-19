"""The files a person should look at before deposit, judged from an inventory's names, sizes and
digests alone (#449, #1072).

An inventory never holds contents, so a hint is a prompt for a person, never a finding: a file
with none may still hold personal data, sensitive locations or someone else's material
(docs/specs/personal-data.md). The rules are in `hints.yaml`, which `inventory/browser/src/hints.ts`
copies so that the app marks the same files; change both together.

`file_hints` reads an inventory's files in their JSON form (`inventory_files`, as `dd-inventory`
writes them), so that it needs nothing of the Data Director contract: the File Archivist lists
every hint, and the drafters use `deposit_hints` to keep out of a drafted document the files a
person would rarely deposit, and to ask about the ones a person must decide on, so that no draft
presents either as the dataset's contents.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any

import yaml

WORD = re.compile(r"[a-z]+")


class HintKind(StrEnum):
    """What a file's names, size or digest suggest a person should check."""

    FREE_TEXT = "free_text"
    COORDINATES = "coordinates"
    THIRD_PARTY = "third_party"
    GOVERNANCE = "governance"
    SYSTEM_FILE = "system_file"
    EMPTY = "empty"
    DUPLICATE = "duplicate"


# A file with one of these is rarely part of a dataset: a draft proposes leaving it out. Of a set
# of byte-for-byte copies, one is kept (`deposit_hints`).
LEAVE_OUT = frozenset({HintKind.SYSTEM_FILE, HintKind.EMPTY, HintKind.DUPLICATE})
# A file with one of these may be part of the dataset, but a person must decide before deposit.
DECIDE = frozenset(
    {HintKind.FREE_TEXT, HintKind.COORDINATES, HintKind.THIRD_PARTY, HintKind.GOVERNANCE}
)


@dataclass(frozen=True)
class Rule:
    """One kind of hint in `hints.yaml`."""

    kind: HintKind
    question: str
    within: frozenset[str] = frozenset()
    words: frozenset[str] = frozenset()
    names: frozenset[str] = frozenset()
    prefixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Hint:
    """One reason to look at one file: the word or name that called for it, if any, what a person
    should check, and for a copy, the other files with the same digest."""

    path: str
    kind: HintKind
    question: str
    matched: str | None = None
    related_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class DepositHints:
    """What a drafter does with an inventory's hints: the files it proposes to leave out, and the
    files a person must decide on, each with the hints that put it there, by path in the
    inventory's order. A file in neither is drafted as usual."""

    leave_out: dict[str, list[Hint]] = field(default_factory=dict)
    decide: dict[str, list[Hint]] = field(default_factory=dict)


def load_rules(text: str | None = None) -> tuple[Rule, ...]:
    """The rules of `hints.yaml`, or of `text` in its form, in the order they are checked."""
    if text is None:
        text = files("dd_inventory").joinpath("hints.yaml").read_text("utf-8")
    table = yaml.safe_load(text)
    return tuple(
        Rule(
            kind=HintKind(kind),
            question=" ".join(str(row["question"]).split()),
            within=frozenset(row.get("in", ())),
            words=frozenset(str(w).lower() for w in row.get("words", ())),
            names=frozenset(str(n).lower() for n in row.get("names", ())),
            prefixes=tuple(str(p).lower() for p in row.get("prefixes", ())),
        )
        for kind, row in table.items()
    )


def file_hints(
    inventory_files: Iterable[Mapping[str, Any]], rules: Sequence[Rule] | None = None
) -> list[Hint]:
    """Every hint for the files, in the order of the files and, for each file, of the rules."""
    rules = rules if rules is not None else load_rules()
    listed = list(inventory_files)
    copies: dict[str, list[str]] = defaultdict(list)
    for f in listed:
        if f.get("file_sha256") and f.get("file_size"):
            copies[f["file_sha256"]].append(f["file_path"])
    return [hint for f in listed for rule in rules if (hint := _hint(rule, f, copies)) is not None]


def deposit_hints(
    inventory_files: Iterable[Mapping[str, Any]], rules: Sequence[Rule] | None = None
) -> DepositHints:
    """The files a draft proposes to leave out, and those a person must decide on (#1072).

    A system file, an empty file or a copy is left out, except that of a set of copies one is kept:
    the one nearest the top of the folders, then with the shortest path, then the first listed. A
    file left out is not also asked about. Nothing is dropped unsaid: a drafter lists each file
    left out with its hints."""
    listed = list(inventory_files)
    hints = file_hints(listed, rules)
    kept = _kept_copies(listed)
    by_path: dict[str, list[Hint]] = defaultdict(list)
    for hint in hints:
        by_path[hint.path].append(hint)
    result = DepositHints()
    for f in listed:
        path = f["file_path"]
        found = by_path.get(path, [])
        leave = [
            h
            for h in found
            if h.kind in LEAVE_OUT and not (h.kind == HintKind.DUPLICATE and path in kept)
        ]
        if leave:
            result.leave_out[path] = leave
            continue
        decide = [h for h in found if h.kind in DECIDE]
        if decide:
            result.decide[path] = decide
    return result


def _kept_copies(listed: Sequence[Mapping[str, Any]]) -> set[str]:
    """Of each set of byte-for-byte copies, the one a draft keeps."""
    groups: dict[str, list[tuple[int, int, int, str]]] = defaultdict(list)
    for i, f in enumerate(listed):
        digest, path = f.get("file_sha256"), f["file_path"]
        if digest and f.get("file_size"):
            groups[digest].append((len(PurePosixPath(path).parts), len(path), i, path))
    return {min(group)[3] for group in groups.values()}


def _words(*names: str) -> Iterator[str]:
    for name in names:
        yield from WORD.findall(name.lower())


def _hint(rule: Rule, f: Mapping[str, Any], copies: Mapping[str, list[str]]) -> Hint | None:
    path = str(f["file_path"])
    if rule.kind == HintKind.EMPTY:
        return Hint(path, rule.kind, rule.question) if f.get("file_size") == 0 else None
    if rule.kind == HintKind.DUPLICATE:
        others = tuple(p for p in copies.get(f.get("file_sha256") or "", ()) if p != path)
        return Hint(path, rule.kind, rule.question, related_paths=others) if others else None
    parts = PurePosixPath(path)
    name = parts.name.lower()
    if name in rule.names or (bool(rule.prefixes) and name.startswith(rule.prefixes)):
        return Hint(path, rule.kind, rule.question, matched=parts.name)
    places: list[str] = []
    if "folders" in rule.within:
        places += parts.parts[:-1]
    if "file" in rule.within:
        places.append(parts.name)
    if "fields" in rule.within:
        places += [str(c.get("name", "")) for c in f.get("file_fields") or ()]
    for word in _words(*places):
        if word in rule.words:
            return Hint(path, rule.kind, rule.question, matched=word)
    return None

"""Name-level hints: the files of an inventory whose folder, file or field names, size or digest
call for a person to look at them before deposit (docs/specs/personal-data.md, #449).

The inventory never holds file contents, so a hint is a prompt for a person, never a finding: a
file with no hint may still hold personal data, sensitive locations or someone else's material.
The File Archivist (`advisor.files`) lists the hints with its advice, and the harness's deposit
check asks a person to decide each one before packaging (docs/specs/deposit.md). Both read this one
table. The app's inventory view marks the same files from its own copy,
`inventory/browser/src/hints.ts`, which this package cannot share: keep the two in step.

Each kind is checked in the order of `RULES`. `words` are matched as whole lower-case words of the
parts named by `within`: `folders` (each folder in the path), `file` (the file name) or `fields`
(a table's field names). `names` are whole file names, case ignored; `prefixes` begin a file name
and `suffixes` end one, such as an extension.
`empty` and `duplicate` are judged from size and digest.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from dd_sdk.contract.inventory import InventoryFile

WORD = re.compile(r"[a-z]+")


class HintKind(StrEnum):
    FREE_TEXT = "free_text"
    COORDINATES = "coordinates"
    THIRD_PARTY = "third_party"
    GOVERNANCE = "governance"
    SYSTEM_FILE = "system_file"
    CREDENTIALS = "credentials"
    EMPTY = "empty"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class Rule:
    """One kind of hint, and what calls for it."""

    kind: HintKind
    question: str
    within: frozenset[str] = frozenset()
    words: frozenset[str] = frozenset()
    names: frozenset[str] = frozenset()
    prefixes: tuple[str, ...] = ()
    suffixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Hint:
    """A file a person should look at, why, and the word or name that called for it."""

    path: str
    kind: HintKind
    question: str
    matched: str | None = None
    related_paths: tuple[str, ...] = ()


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


RULES: tuple[Rule, ...] = (
    Rule(
        HintKind.FREE_TEXT,
        "Its name suggests free text, which often holds names, telephone numbers, access codes or "
        "instructions. Read it before it is shared, and decide whether to leave it out or share a "
        "redacted copy.",
        within=frozenset({"folders", "file"}),
        words=_words(
            "notes fieldnotes fieldnote diary diaries journal notebook logbook interview "
            "interviews transcript transcripts consent correspondence email emails letters minutes"
        ),
    ),
    Rule(
        HintKind.COORDINATES,
        "A field name suggests coordinates or a location. Precise locations may expose people, "
        "private land or protected species: a person decides whether to publish, generalise or "
        "withhold them.",
        within=frozenset({"fields"}),
        words=_words(
            "lat lon lng latitude longitude easting northing eastings northings gridref coord "
            "coords coordinates gps geom geometry location"
        ),
    ),
    Rule(
        HintKind.THIRD_PARTY,
        "It is in a folder whose name suggests material from someone else, which may come under "
        "its own licence or terms. Check who holds the rights before it is included.",
        within=frozenset({"folders"}),
        words=_words(
            "reference references external thirdparty third vendor downloaded purchased licensed "
            "bought supplied"
        ),
    ),
    Rule(
        HintKind.GOVERNANCE,
        "Its name suggests terms or an agreement. Check what it allows and whether it is still in "
        "force before deposit.",
        within=frozenset({"folders", "file"}),
        words=_words(
            "agreement agreements licence license licences licenses permission permissions "
            "contract contracts governance dpa dsa nda terms"
        ),
    ),
    Rule(
        HintKind.SYSTEM_FILE,
        "Its name is that of a file an operating system or program makes for itself. It is rarely "
        "part of a dataset: leave it out unless it is.",
        names=frozenset({"thumbs.db", "desktop.ini", ".ds_store", "ehthumbs.db"}),
        prefixes=("~$", "._"),
    ),
    Rule(
        HintKind.CREDENTIALS,
        "Its name is that of a configuration or credentials file, which may hold passwords, keys "
        "or tokens. Check whether it does, and if so leave it out of the deposit.",
        within=frozenset({"file"}),
        words=_words(
            "config secret secrets credential credentials password passwords token tokens apikey"
        ),
        names=_words(
            ".env .netrc .pgpass .htpasswd .pypirc .npmrc .git-credentials .s3cfg id_rsa id_dsa "
            "id_ecdsa id_ed25519 credentials credentials.json secrets.yaml secrets.yml secrets.json"
        ),
        suffixes=(
            ".ini",
            ".cfg",
            ".conf",
            ".env",
            ".pem",
            ".key",
            ".p12",
            ".pfx",
            ".keystore",
            ".jks",
        ),
    ),
    Rule(HintKind.EMPTY, "The file is empty. Leave it out, or find what it should hold."),
    Rule(
        HintKind.DUPLICATE,
        "It has the same digest as another file, so the two are byte-for-byte copies. Keep one.",
    ),
)


def hints(files: Sequence[InventoryFile], rules: Sequence[Rule] = RULES) -> list[Hint]:
    """Every hint for `files`, file by file in their order, and for each file in the order of
    `rules`."""
    copies: dict[str, list[str]] = defaultdict(list)
    for file in files:
        if file.file_sha256 and file.file_size:
            copies[file.file_sha256].append(file.file_path)
    found = []
    for file in files:
        for rule in rules:
            hint = _check(rule, file, copies)
            if hint is not None:
                found.append(hint)
    return found


def _check(rule: Rule, file: InventoryFile, copies: dict[str, list[str]]) -> Hint | None:
    if rule.kind == HintKind.EMPTY:
        return Hint(file.file_path, rule.kind, rule.question) if file.file_size == 0 else None
    if rule.kind == HintKind.DUPLICATE:
        others = tuple(p for p in copies.get(file.file_sha256 or "", ()) if p != file.file_path)
        if not others:
            return None
        return Hint(file.file_path, rule.kind, rule.question, related_paths=others)
    return _named(rule, file)


def _named(rule: Rule, file: InventoryFile) -> Hint | None:
    """A hint whose file's name, or a word in its folders, name or fields, the rule names."""
    path = PurePosixPath(file.file_path)
    name = path.name.lower()
    if name in rule.names or name.startswith(rule.prefixes) or name.endswith(rule.suffixes):
        return Hint(file.file_path, rule.kind, rule.question, matched=path.name)
    places: list[str] = []
    if "folders" in rule.within:
        places += path.parts[:-1]
    if "file" in rule.within:
        places.append(path.name)
    if "fields" in rule.within:
        places += [f.name for f in file.file_fields]
    for word in _split(*places):
        if word in rule.words:
            return Hint(file.file_path, rule.kind, rule.question, matched=word)
    return None


def _split(*names: str) -> Iterator[str]:
    for name in names:
        yield from WORD.findall(name.lower())

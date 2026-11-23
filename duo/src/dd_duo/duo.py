"""The pinned DUO release, read from `data/` beside this module."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from functools import cache
from importlib import resources
from typing import Any, Literal

Kind = Literal["permission", "modifier"]


class PinError(Exception):
    """The packaged terms do not match their manifest: the package is damaged, not the input."""


@dataclass(frozen=True)
class Term:
    """One data use permission or modifier as the pinned release defines it.

    `shorthand` is DUO's code, such as `IRB`, where it gives one. `parent` is the broader DUO term,
    if any, and `url` the term's persistent IRI.
    """

    id: str
    shorthand: str | None
    label: str
    definition: str
    kind: Kind
    parent: str | None
    url: str

    def as_dict(self) -> dict[str, Any]:
        """The term as it is stored: one line of the release's JSONL file."""
        return asdict(self)


@dataclass(frozen=True)
class Release:
    """Which DUO release the terms come from, and the SHA-256 of the terms file."""

    version: str
    file: str
    sha256: str
    licence: str
    source: str


def _read(name: str) -> bytes:
    return resources.files("dd_duo").joinpath("data", name).read_bytes()


@cache
def release() -> Release:
    """The pinned release, from `data/manifest.json`."""
    manifest = json.loads(_read("manifest.json"))
    return Release(
        version=str(manifest["duo_version"]),
        file=str(manifest["terms"]["file"]),
        sha256=str(manifest["terms"]["sha256"]),
        licence=str(manifest["licence"]),
        source=str(manifest["source"]),
    )


def _parse(raw: bytes) -> tuple[Term, ...]:
    return tuple(Term(**json.loads(line)) for line in raw.decode("utf-8").splitlines() if line)


@cache
def _terms() -> tuple[Term, ...]:
    pinned = release()
    raw = _read(pinned.file)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != pinned.sha256:
        raise PinError(f"{pinned.file} has sha256 {digest}, not the pinned {pinned.sha256}")
    return _parse(raw)


@cache
def _by_key() -> dict[str, Term]:
    keys: dict[str, Term] = {}
    for term in _terms():
        keys[term.id] = term
        if term.shorthand:
            keys[term.shorthand.upper()] = term
    return keys


def lookup(key: str) -> Term | None:
    """The term with identifier (`DUO:0000021`) or shorthand (`IRB`) `key`, or None if the pinned
    release has no current term by that name."""
    return _by_key().get(key.strip().upper())


def terms(kind: Kind | None = None) -> tuple[Term, ...]:
    """The pinned release's current terms in identifier order, of one kind if given."""
    return tuple(t for t in _terms() if kind is None or t.kind == kind)

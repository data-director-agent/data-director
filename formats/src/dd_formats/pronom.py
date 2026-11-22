"""The pinned PRONOM release, read from `data/` beside this module."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any


class PinError(Exception):
    """The packaged data do not match their manifest: the package is damaged, not the input."""


@dataclass(frozen=True)
class FormatRecord:
    """One format as the pinned PRONOM release records it.

    `version` is None where PRONOM gives none. `superseded_by` names the PUID that replaces a
    deprecated one. `url` is the record's page at The National Archives.
    """

    puid: str
    name: str
    version: str | None
    media_types: tuple[str, ...]
    extensions: tuple[str, ...]
    superseded_by: str | None
    url: str

    def as_dict(self) -> dict[str, Any]:
        """The record as it is stored: one line of the release's JSONL file."""
        return {
            "puid": self.puid,
            "name": self.name,
            "version": self.version,
            "media_types": list(self.media_types),
            "extensions": list(self.extensions),
            "superseded_by": self.superseded_by,
            "url": self.url,
        }


@dataclass(frozen=True)
class Release:
    """Which PRONOM release the records come from, and the SHA-256 of the records file."""

    version: int
    created: str
    file: str
    sha256: str
    licence: str
    source: str


def _data(name: str) -> bytes:
    return resources.files("dd_formats").joinpath("data", name).read_bytes()


@cache
def release() -> Release:
    """The pinned release, from `data/manifest.json`."""
    manifest = json.loads(_data("manifest.json"))
    return Release(
        version=int(manifest["pronom_version"]),
        created=str(manifest["release_created"]),
        file=str(manifest["records"]["file"]),
        sha256=str(manifest["records"]["sha256"]),
        licence=str(manifest["licence"]),
        source=str(manifest["source"]),
    )


@cache
def _index() -> Mapping[str, FormatRecord]:
    pinned = release()
    raw = _data(pinned.file)
    actual = hashlib.sha256(raw).hexdigest()
    if actual != pinned.sha256:
        raise PinError(f"{pinned.file} has sha256 {actual}, not the pinned {pinned.sha256}")
    index: dict[str, FormatRecord] = {}
    for line in raw.decode("utf-8").splitlines():
        row = json.loads(line)
        index[row["puid"]] = FormatRecord(
            puid=row["puid"],
            name=row["name"],
            version=row["version"],
            media_types=tuple(row["media_types"]),
            extensions=tuple(row["extensions"]),
            superseded_by=row["superseded_by"],
            url=row["url"],
        )
    return index


def lookup(puid: str) -> FormatRecord | None:
    """The record for `puid`, or None if the pinned release has no such PUID.

    A deprecated PUID gives the record of the PUID that replaces it, where PRONOM names one, so
    that the format is described by its current record; otherwise its own.
    """
    index = _index()
    found = index.get(puid)
    if found is not None and found.superseded_by is not None:
        return index.get(found.superseded_by, found)
    return found


def records() -> Iterator[FormatRecord]:
    """Every record of the pinned release, in PUID order, deprecated ones included."""
    return iter(_index().values())

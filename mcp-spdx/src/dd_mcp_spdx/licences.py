"""The pinned SPDX licence-list release, read from `data/` beside this module."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any


class PinError(Exception):
    """The packaged data do not match their manifest: the package is damaged, not the input."""


@dataclass(frozen=True)
class Release:
    """Which licence-list release the records come from, and the SHA-256 of the records file."""

    version: str
    released: str
    file: str
    sha256: str
    count: int

    @property
    def snapshot_ref(self) -> str:
        """The label a deployment pins this copy under, such as `spdx:3.29.0`."""
        return f"spdx:{self.version}"


def _data(name: str) -> bytes:
    return resources.files("dd_mcp_spdx").joinpath("data", name).read_bytes()


@cache
def release() -> Release:
    """The pinned release, from `data/manifest.json`."""
    manifest = json.loads(_data("manifest.json"))
    return Release(
        version=str(manifest["licence_list_version"]),
        released=str(manifest["release_date"]),
        file=str(manifest["records"]["file"]),
        sha256=str(manifest["records"]["sha256"]),
        count=int(manifest["records"]["count"]),
    )


def index(pinned: Release, raw: bytes) -> Mapping[str, dict[str, Any]]:
    """The records in `raw`, by case-folded identifier, once `raw` is shown to be `pinned`'s."""
    if hashlib.sha256(raw).hexdigest() != pinned.sha256:
        raise PinError(f"{pinned.file} does not match its manifest: the package is damaged")
    records = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line]
    if len(records) != pinned.count:
        raise PinError(f"{pinned.file} holds {len(records)} records, not {pinned.count}")
    return {str(r["licenseId"]).casefold(): r for r in records}


@cache
def _packaged() -> Mapping[str, dict[str, Any]]:
    pinned = release()
    return index(pinned, _data(pinned.file))


def licence(spdx_id: str) -> dict[str, Any] | None:
    """The record for `spdx_id`, matched without regard to case as SPDX matches identifiers, or
    None if the pinned release has no such licence."""
    found = _packaged().get(spdx_id.strip().casefold())
    return None if found is None else dict(found)

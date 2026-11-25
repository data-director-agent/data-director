"""The kinds of data a project's inventory names, read through `kinds.yaml` (#1560).

In a project the conductor gives `RepositoryNeeds` the project's inventory
(`project_file_inventory`, docs/specs/projects.md). When the needs give no kinds of data, they are
taken from the media types the inventory identified its files as: each kind once, in the order its
first file is listed. A file with no media type, or one the table does not know, names no kind;
how many files named none is said, so the researcher can tell what the search rests on. Kinds the
caller gave always stand.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from dd_sdk.contract.inventory import FileInventory

KINDS = Path(__file__).with_name("kinds.yaml")


@cache
def _table() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(KINDS.read_text(encoding="utf-8"))
    return data


def kind(media_type: str) -> str | None:
    """The kind of data `media_type` names, as written or by its top-level type, or None."""
    table = _table()
    bare = media_type.split(";", 1)[0].strip().casefold()
    found = table["media_types"].get(bare)
    if found is None:
        found = table["top_level"].get(bare.split("/", 1)[0])
    return str(found) if found is not None else None


@dataclass(frozen=True)
class FromInventory:
    """The kinds of data an inventory names, and how many of its files named none."""

    kinds: list[str]
    unnamed: int

    def said(self) -> str:
        """A sentence for the outcome, on what the search took from the inventory."""
        listed = ", ".join(f'"{k}"' for k in self.kinds) or "none"
        unnamed = (
            f"; {self.unnamed} of its files had a media type that names no kind"
            if self.unnamed
            else ""
        )
        return f" Kinds of data taken from the project's inventory: {listed}{unnamed}."


def from_inventory(inventory: FileInventory) -> FromInventory:
    """The kinds of data `inventory`'s files' media types name, each once."""
    kinds: dict[str, None] = {}
    unnamed = 0
    for file in inventory.inventory_files:
        named = kind(file.file_media_type) if file.file_media_type else None
        if named is None:
            unnamed += 1
        else:
            kinds.setdefault(named)
    return FromInventory(list(kinds), unnamed)

"""Walk a dataset's root folder and make its `FileInventory` (ADR-0034).

The inventory is a plain JSON document of the core contract class `FileInventory`; this package
does not need the contract to make one. Paths are relative to the root and sorted, so two runs
over the same files differ only in `inventory_made_at`.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from typing import Any

from dd_inventory.identify import Identifier, default_identifier
from dd_inventory.tables import TableError, is_table, table_fields

TOOL = "dd-inventory"
SCHEMA_CLASS = "FileInventory"


def tool_version() -> str:
    return version("data-director-inventory")


def sha256(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def _walk(root: Path) -> tuple[list[Path], list[str]]:
    """Every regular file under `root`, and what was left out. Hidden files and links are not
    followed: a link may point outside the dataset, and a hidden file is rarely part of it."""
    found: list[Path] = []
    hidden = links = 0
    for folder, dirs, names in os.walk(root, followlinks=False):
        here = Path(folder)
        for d in list(dirs):
            if d.startswith(".") or (here / d).is_symlink():
                hidden += d.startswith(".")
                links += not d.startswith(".")
                dirs.remove(d)
        for name in names:
            path = here / name
            if name.startswith("."):
                hidden += 1
            elif path.is_symlink():
                links += 1
            elif path.is_file():
                found.append(path)
    skipped = []
    if hidden:
        skipped.append(
            f"{hidden} hidden file(s) or folder(s), whose names begin with '.', were skipped."
        )
    if links:
        skipped.append(f"{links} symbolic link(s) were not followed.")
    return sorted(found, key=lambda p: p.relative_to(root).as_posix()), skipped


def make_inventory(
    root: Path, *, identifier: Identifier | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """The `FileInventory` of every file under `root`, as a JSON-ready dict."""
    root = root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    limitations: list[str] = []
    if identifier is None:
        identifier, unavailable = default_identifier()
        if unavailable:
            limitations.append(f"{unavailable}; formats were guessed from file extensions only.")
    paths, skipped = _walk(root)
    limitations += skipped
    files = []
    for path in paths:
        try:
            files.append(_describe(root, path, identifier, limitations))
        except OSError as exc:
            limitations.append(
                f"{path.relative_to(root).as_posix()} could not be read: {exc.strerror}."
            )
    limitations.append(
        "Table fields are inferred from a sample of rows; a later row may not fit the type given."
    )
    made_at = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    return {
        "schema_class": SCHEMA_CLASS,
        "inventory_files": files,
        "inventory_tool": TOOL,
        "inventory_tool_version": tool_version(),
        "inventory_identified_with": identifier.description,
        "inventory_made_at": made_at,
        "inventory_limitations": limitations,
    }


def _describe(
    root: Path, path: Path, identifier: Identifier, limitations: list[str]
) -> dict[str, Any]:
    relative = PurePosixPath(path.relative_to(root).as_posix())
    found = identifier.identify(path)
    entry: dict[str, Any] = {
        "file_path": str(relative),
        "file_size": path.stat().st_size,
        "file_sha256": sha256(path),
    }
    if found.media_type:
        entry["file_media_type"] = found.media_type
    entry["file_pronom_ids"] = found.pronom_ids
    entry["file_identified_by"] = found.method
    if is_table(path):
        try:
            entry["file_fields"] = table_fields(path)
        except TableError as exc:
            limitations.append(f"The fields of {relative} could not be inferred: {exc}")
    return entry

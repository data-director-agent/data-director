"""Walk a dataset's root folder and make its `FileInventory` (docs/specs/projects.md).

The inventory is a plain JSON document of the core contract class `FileInventory`; this package
does not need the contract to make one. Paths are relative to the root and sorted, so two runs
over the same files differ only in `inventory_made_at`.

The same code runs in a browser under Pyodide. There the inventory's tool version carries a local
version label naming the runtime, such as `0.1.0a3+pyodide.314.0.7`, so that it can be told from
the command's.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from typing import Any, Final

from dd_inventory.identify import Identifier, default_identifier
from dd_inventory.tables import TableError, is_table, table_fields

TOOL = "dd-inventory"
SCHEMA_CLASS = "FileInventory"


class _Detect:
    """The default of `make_inventory`'s `runtime`: detect it, as opposed to `None`, native."""


DETECT: Final = _Detect()


@dataclass(frozen=True)
class FileProgress:
    """One file handled by `make_inventory`: its path relative to the root, its size in bytes
    (0 if it could not be read), and how many of the `total` files are done, this one included."""

    path: str
    size: int
    done: int
    total: int


def detect_runtime() -> str | None:
    """The runtime this code runs in, as a version label, or `None` when it runs natively."""
    platform: str = sys.platform  # read at call time, so that type checkers do not fix it
    if platform != "emscripten":
        return None
    try:
        import pyodide  # type: ignore[import-not-found]  # only under Pyodide
    except ImportError:
        return "emscripten"
    return "pyodide." + re.sub(r"[^A-Za-z0-9.]+", ".", str(pyodide.__version__)).strip(".")


def tool_version(runtime: str | None = None) -> str:
    """The command's version, with the runtime as a local version label when one is given."""
    base = version("data-director-inventory")
    return f"{base}+{runtime}" if runtime else base


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
    root: Path,
    *,
    identifier: Identifier | None = None,
    now: datetime | None = None,
    runtime: str | _Detect | None = DETECT,
    on_file: Callable[[FileProgress], None] | None = None,
) -> dict[str, Any]:
    """The `FileInventory` of every file under `root`, as a JSON-ready dict.

    `runtime` names the runtime in the tool version; by default it is detected, and `None` means
    native. `on_file`, if given, is called once per file, in order, after the file is handled.
    """
    if isinstance(runtime, _Detect):
        runtime = detect_runtime()
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
    for done, path in enumerate(paths, start=1):
        relative = path.relative_to(root).as_posix()
        size = 0
        try:
            entry = _describe(root, path, identifier, limitations)
            files.append(entry)
            size = entry["file_size"]
        except OSError as exc:
            limitations.append(f"{relative} could not be read: {exc.strerror}.")
        if on_file is not None:
            on_file(FileProgress(path=relative, size=size, done=done, total=len(paths)))
    limitations.append(
        "Table fields are inferred from a sample of rows; a later row may not fit the type given."
    )
    made_at = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    return {
        "schema_class": SCHEMA_CLASS,
        "inventory_files": files,
        "inventory_tool": TOOL,
        "inventory_tool_version": tool_version(runtime),
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

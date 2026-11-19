"""Describing a folder on the machine the app runs on, read only and only under the folders the
deployment lists (docs/specs/projects.md, The inventory command).

`DD_INVENTORY_FOLDERS` lists those folders, separated by the system's path separator (`:` on
Linux and macOS, `;` on Windows). It is for an app installed on the researcher's own machine: set
on an app that listens beyond loopback, nothing may run, so the shared deployment can never
describe its own disk. Unset, the app offers nothing here.

A folder is named by the root it is under and a path relative to that root. Listing one gives
the names of its subfolders and never of its files; describing one runs `dd_inventory`'s own
`make_inventory`, which follows no link and reads no hidden file. Neither records anything: the
inventory goes to the researcher's check like any other (docs/specs/app.md).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from dd_inventory import make_inventory
from dd_sdk.credentials import ConfigError

VARIABLE = "DD_INVENTORY_FOLDERS"


class FolderRefusedError(ValueError):
    """A folder that is not one the app may read: unknown root, outside it, or not a folder."""


@dataclass(frozen=True)
class FolderRoots:
    """The folders the app may describe, each under the name the researcher sees."""

    roots: Mapping[str, Path]

    @property
    def names(self) -> list[str]:
        return list(self.roots)

    def resolve(self, root: str, relative: str = "") -> Path:
        """The folder `relative` names under `root`, or `FolderRefusedError`. The path is relative,
        with forward slashes; it must resolve, links followed, to a folder under the root."""
        base = self.roots.get(root)
        if base is None:
            raise FolderRefusedError(f"{root!r} is not a folder this app may describe")
        parts = PurePosixPath(relative).parts if relative else ()
        if relative.startswith("/") or "\\" in relative or ".." in parts:
            raise FolderRefusedError(f"{relative!r} is not a path relative to {root!r}")
        try:
            path = base.joinpath(*parts).resolve(strict=True)
        except OSError as exc:
            raise FolderRefusedError(f"{relative!r} is not a folder under {root!r}") from exc
        if not path.is_relative_to(base) or not path.is_dir():
            raise FolderRefusedError(f"{relative!r} is not a folder under {root!r}")
        return path

    def subfolders(self, root: str, relative: str = "") -> list[str]:
        """The names of the folders directly in `relative`, skipping hidden ones and links as
        `dd_inventory` does; never a file's name."""
        path = self.resolve(root, relative)
        return sorted(
            entry.name
            for entry in os.scandir(path)
            if not entry.name.startswith(".")
            and not entry.is_symlink()
            and entry.is_dir(follow_symlinks=False)
        )

    def describe(self, root: str, relative: str = "") -> dict[str, Any]:
        """The `FileInventory` of the folder, made natively by `dd_inventory`."""
        return make_inventory(self.resolve(root, relative), runtime=None)


def from_env(env: Mapping[str, str], host: str, loopback: frozenset[str]) -> FolderRoots | None:
    """The folders `DD_INVENTORY_FOLDERS` lists, or None when it lists none.

    A listed folder that is not an existing absolute folder, or a list given to an app that
    listens on `host` beyond `loopback`, is a `ConfigError`.
    """
    listed = [p for p in env.get(VARIABLE, "").split(os.pathsep) if p.strip()]
    if not listed:
        return None
    if host not in loopback:
        raise ConfigError(
            f"{VARIABLE} is for an app on the researcher's own machine, "
            f"but this one listens on {host}; unset it, or listen on loopback"
        )
    roots: dict[str, Path] = {}
    for entry in listed:
        path = Path(entry.strip())
        if not path.is_absolute() or not path.is_dir():
            raise ConfigError(f"{VARIABLE}: {entry!r} is not an absolute path to a folder")
        resolved = path.resolve()
        name = resolved.name or str(resolved)
        unique, n = name, 2
        while unique in roots:
            unique, n = f"{name} ({n})", n + 1
        roots[unique] = resolved
    return FolderRoots(roots)

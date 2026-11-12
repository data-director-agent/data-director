"""Every way the admin service reaches outside its own process but the stores, behind one class
that tests replace: running a command, fetching a URL, and reading a file or directory."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx

COMMAND_TIMEOUT_S = 60.0
HTTP_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class Done:
    """What a command did: its exit status and what it printed (standard output, then error)."""

    status: int
    out: str
    err: str = ""


class System:
    """The real machine. Nothing here writes: the admin service only reads."""

    def run(self, *cmd: str, timeout_s: float = COMMAND_TIMEOUT_S) -> Done:
        """Run `cmd` without a shell. A command that cannot start, or runs too long, is a
        `Done` with status 127 or 124 and the reason, as a shell would report it."""
        try:
            done = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_s, check=False
            )
        except FileNotFoundError as exc:
            return Done(127, "", f"{cmd[0]}: {exc.strerror}")
        except subprocess.TimeoutExpired:
            return Done(124, "", f"{cmd[0]}: no answer within {timeout_s:.0f} s")
        return Done(done.returncode, done.stdout, done.stderr)

    def get_json(self, url: str, headers: Mapping[str, str] | None = None) -> object | None:
        """The JSON document at `url`, or None if it cannot be fetched or is not JSON."""
        try:
            response = httpx.get(url, headers=dict(headers or {}), timeout=HTTP_TIMEOUT_S)
            response.raise_for_status()
            found: object = response.json()
        except httpx.HTTPError, ValueError:
            return None
        return found

    def read_text(self, path: Path) -> str | None:
        """The file's text, or None if it is missing or this user may not read it."""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def list_dir(self, path: Path) -> list[Path] | None:
        """The entries of a directory, sorted by name, or None if it cannot be listed."""
        try:
            return sorted(path.iterdir())
        except OSError:
            return None

    def resolve(self, path: Path) -> Path | None:
        """Where a link points, or None if it does not exist."""
        try:
            return path.resolve(strict=True)
        except OSError:
            return None

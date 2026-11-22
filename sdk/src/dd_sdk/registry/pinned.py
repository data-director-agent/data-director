"""A registry built from one archive pinned by URL and SHA-256 (docs/specs/grounding.md).

Some registries are too large to commit, so an agent pins one published archive (a monthly
re3data export, a ROR data dump) in a `manifest.json` and builds a JSON Lines registry from it
where it runs. The manifest pins the archive's SHA-256 and the built registry's, so the same
archive always builds the same bytes and a deployment's `sources.yaml` can pin them too.

This module holds the steps every such agent repeats: reading and writing the pin, hashing,
downloading an archive at most once per pin (Blueprint P14), writing the registry atomically and
saying why a built registry does not match its pin. A download the server fails (a 5xx or 429,
or no answer) is tried again after a pause, so that a publisher's brief outage does not fail a
build; any other status fails at once. What the archive holds and how it is parsed
stays with the agent. Each function raises the agent's own error class, a `PinError`, whose
message says what to do.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Protocol

import httpx

from dd_sdk.sources import PREPARE_COMMAND

PROJECT_URL = "https://github.com/data-director-agent/data-director"


class PinError(Exception):
    """A registry cannot be built or read as pinned. The message says what to do."""


class Pinned(Protocol):
    """What every pin records: the archive, its hash, and the hash of the registry built from it."""

    @property
    def archive(self) -> str: ...

    @property
    def archive_sha256(self) -> str: ...

    @property
    def snapshot_sha256(self) -> str: ...


def read_pin[P](cls: Callable[..., P], path: Path, what: str, error: type[Exception]) -> P:
    """The pin in `path`, as `cls`; `error` naming `what` if it cannot be read."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)
    except (OSError, ValueError, TypeError) as exc:
        raise error(f"{what} pin {path} cannot be read: {exc}") from None


def write_pin(pin: Any, path: Path) -> None:
    """Write a dataclass pin as indented JSON, in field order."""
    text = json.dumps(asdict(pin), indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def same_pin(current: Pinned | None, new: Pinned) -> bool:
    """Whether `new` pins the same archive, building the same bytes, as `current`. If so the
    agent keeps `current`, and its date, so that pinning it again changes nothing."""
    return current is not None and (
        current.archive,
        current.archive_sha256,
        current.snapshot_sha256,
    ) == (new.archive, new.archive_sha256, new.snapshot_sha256)


def sha256_file(path: Path) -> str:
    """The SHA-256 of a file, read in chunks, so a large archive is never held whole."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def problem(registry: Path, snapshot_sha256: str, name: str, pinned: str) -> str | None:
    """Why the registry built at `registry` cannot be used as pinned, or None when it can.
    `name` names the registry and `pinned` the archive, as "the pinned dump v2.15"."""
    if not registry.is_file():
        return f"the {name} registry is not built at {registry}; run `{PREPARE_COMMAND}`"
    if sha256_file(registry) != snapshot_sha256:
        return f"the {name} registry at {registry} does not match {pinned}; run `{PREPARE_COMMAND}`"
    return None


def user_agent(distribution: str, product: str, contact: str | None = None) -> str:
    """A `User-Agent` that names the project and where to find it, never a person. `contact`, a
    deployment's operators' address, is added as `mailto:` for registries that serve identified
    clients faster; the caller checks it is one plain address."""
    try:
        ours = version(distribution)
    except PackageNotFoundError:
        ours = "unknown"
    mailto = f"; mailto:{contact}" if contact else ""
    return f"{product}/{ours} (+{PROJECT_URL}{mailto})"


@dataclass(frozen=True)
class Downloader:
    """How an agent downloads from its registry: its `User-Agent`, its timeout, and the error it
    raises. A client passed to a method is used as it is and left open; otherwise one is made
    and closed. `pauses` are the seconds waited before each further attempt after the server
    fails, so there are `len(pauses) + 1` attempts in all."""

    user_agent: str
    timeout: float
    error: type[Exception]
    pauses: tuple[float, ...] = (2.0, 8.0, 30.0)
    sleep: Callable[[float], None] = field(default=time.sleep, repr=False, compare=False)

    def client(self, client: httpx.Client | None) -> tuple[httpx.Client, bool]:
        """`client`, or a new one; and whether the caller owns it and must close it."""
        if client is not None:
            return client, False
        return httpx.Client(
            timeout=self.timeout, follow_redirects=True, headers={"User-Agent": self.user_agent}
        ), True

    def download(self, url: str, dest: Path, client: httpx.Client | None = None) -> None:
        """Stream `url` to `dest`, renamed into place only when complete. A failure of the
        server's is tried again after each of `pauses`; the last one raises."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_suffix(".part")
        http, own = self.client(client)
        try:
            for pause in (*self.pauses, None):
                failed = self._attempt(http, url, partial)
                if failed is None:
                    break
                partial.unlink(missing_ok=True)
                if pause is None:
                    raise self.error(failed)
                self.sleep(pause)
        finally:
            if own:
                http.close()
        partial.replace(dest)

    def _attempt(self, http: httpx.Client, url: str, partial: Path) -> str | None:
        """Stream `url` to `partial`: None when done, or why the server failed, worth another
        attempt. Any other status raises at once."""
        try:
            with http.stream("GET", url) as resp:
                if resp.status_code >= 500 or resp.status_code == 429:
                    return f"{url}: HTTP {resp.status_code}"
                if resp.status_code != 200:
                    raise self.error(f"{url}: HTTP {resp.status_code}")
                with partial.open("wb") as fh:
                    for chunk in resp.iter_bytes():
                        fh.write(chunk)
        except httpx.TransportError as exc:
            return f"{url}: {exc}"
        except httpx.HTTPError as exc:
            raise self.error(f"{url}: {exc}") from None
        return None

    def archive(
        self, url: str, sha256: str | None, path: Path, client: httpx.Client | None = None
    ) -> Path:
        """The archive at `url`, kept at `path`: the cached copy when it holds the pinned bytes,
        else downloaded. Downloaded at most once per pin (Blueprint P14).

        A published archive does not change, and a download is renamed into place only when
        complete, so a whole copy is reused when no pin says otherwise. Unpinned, it must at
        least be a zip: a server may answer 200 with a page for an archive not yet published."""
        if path.is_file() and (
            sha256_file(path) == sha256 if sha256 is not None else zipfile.is_zipfile(path)
        ):
            return path
        self.download(url, path, client)
        if sha256 is not None and (actual := sha256_file(path)) != sha256:
            raise self.error(f"{url} has sha256 {actual}, not the pinned {sha256}")
        return path


def write_atomic(path: Path, data: bytes) -> None:
    """Write `data` to `path` through a partial file, so a reader never sees half of it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(path)


def check(found: str | None, ok: str) -> int:
    """A registry command's `check`: print what is wrong, or `ok`; exit 1 if anything is."""
    sys.stdout.write((found or ok) + "\n")
    return 1 if found else 0


@dataclass(frozen=True)
class Installed:
    """A registry written from bytes already built, with the digests its pin records."""

    path: Path
    records: int
    archive_sha256: str
    snapshot_sha256: str


def install(directory: Path, data: bytes, archive: Path) -> Installed:
    """Write a built registry to `directory/registry.jsonl`, as a test's fixture does, and return
    what its pin must record about it and about the `archive` it was built from."""
    path = directory / "registry.jsonl"
    path.write_bytes(data)
    return Installed(
        path=path,
        records=data.count(b"\n"),
        archive_sha256=sha256_file(archive),
        snapshot_sha256=hashlib.sha256(data).hexdigest(),
    )

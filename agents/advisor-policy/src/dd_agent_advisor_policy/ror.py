"""The Research Organization Registry (ROR): which organisation a name means.

ROR (https://ror.org) gives each research organisation a persistent identifier, with its names,
acronyms and aliases, the kinds of organisation it is, and, for funders, the Crossref Funder IDs
it answers to. The policy advisor reads it to identify a funder before it searches FAIRsharing,
so that "NERC" is searched as "Natural Environment Research Council" too, and so that a name that
could mean more than one organisation is asked about rather than guessed.

Two copies answer the same questions through `Organisations`:

- `RorDump` reads `registry.jsonl`, built from one ROR data dump that `manifest.json` pins by URL
  and SHA-256. ROR publishes each dump on Zenodo under CC0 (https://doi.org/10.5281/zenodo.6347574).
  The build keeps only the fields `Organisation` holds, one sorted-key line per organisation,
  sorted by identifier, so the same dump always builds the same bytes and the deployment's
  `sources.yaml` can pin them. Neither the dump nor `registry.jsonl` is committed. `dd-ror fetch`
  downloads the pinned dump once (or uses its cache), verifies it and builds the registry; with
  `--update-pin` it pins the newest dump instead.
- `RorLive` asks ROR's REST API (`api.ror.org/v2`), which needs no account, and keeps the same
  fields, so both copies give the same answer for the same organisation.

A name is matched exactly, ignoring case and spacing, against every name ROR records for an
organisation; only active organisations are matched by name. No alias table is kept here: every
name comes from ROR.

Reading the registry and the API is shared with the PID resolver server (`dd_mcp_pid.ror`, which
the Linking Adviser reads ROR through); this module adds the pin, the build from a dump and the
snapshot each answer is labelled with. It does not use the Data Director contract
(docs/specs/system.md). This module and `live.py` are the importers of `httpx`
(docs/specs/dependencies.md).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import IO, Any, Protocol, runtime_checkable

import httpx
from pydantic import ValidationError

from dd_mcp_pid import ror as shared
from dd_mcp_pid.http import Http, UnavailableError
from dd_mcp_pid.ror_records import Organisation, from_ror_json
from dd_sdk.registry import RegistryUnavailable, SnapshotRef, pinned

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "ror"
MANIFEST = DATA_DIR / "manifest.json"
REGISTRY = DATA_DIR / "registry.jsonl"
ARCHIVES = DATA_DIR / "archives"

API_BASE = shared.API_BASE
# The Zenodo concept record under which ROR publishes every dump, newest first.
ZENODO_RECORDS = "https://zenodo.org/api/records"
ZENODO_CONCEPT = "6347574"
CITATION = "Research Organization Registry (ROR) data dump. https://doi.org/10.5281/zenodo.6347574"
LICENCE = "CC0 1.0 (ROR data); see SOURCE.md"
FETCH_COMMAND = "uv run dd-ror fetch"
TIMEOUT_S = 120.0
# The label of evidence from each copy: the registry, then which copy answered.
REGISTRY_LABEL = "ror"

# Limits on a dump not yet pinned, so a malformed download cannot exhaust memory. The dump of
# 2026-10-20 (v2.15) has 146,716 organisations in 330 MB of JSON, the largest 146 kB.
MAX_JSON_BYTES = 2_000_000_000
MAX_RECORDS = 1_000_000
MAX_RECORD_BYTES = 2_000_000

USER_AGENT = pinned.user_agent("data-director-agent-advisor-policy", "data-director-advisor-policy")


@runtime_checkable
class Organisations(Protocol):
    """ROR, or a copy of it."""

    def snapshot_ref(self) -> SnapshotRef: ...

    def find(self, name: str) -> list[Organisation]:
        """The active organisations with this name, acronym or alias, by identifier. Raises
        RegistryUnavailable when the registry cannot be asked."""
        ...

    def get(self, ror_id: str) -> Organisation | None:
        """The organisation with this identifier (a URL or bare), whatever its status."""
        ...


# --- The pinned dump -----------------------------------------------------------------------


class RorError(pinned.PinError):
    """The registry cannot be built or read as pinned. The message says what to do."""


DOWNLOAD = pinned.Downloader(USER_AGENT, TIMEOUT_S, RorError)


@dataclass(frozen=True)
class Pin:
    version: str
    archive: str
    archive_sha256: str
    doi: str
    records: int
    snapshot_sha256: str
    fetched_at: str
    citation: str = CITATION
    licence: str = LICENCE

    @property
    def label(self) -> str:
        """The evidence's `snapshot_ref` for records from this dump."""
        return f"{REGISTRY_LABEL}:dump:{self.version}"

    @classmethod
    def load(cls, path: Path = MANIFEST) -> Pin:
        return pinned.read_pin(cls, path, "ROR", RorError)

    def write(self, path: Path = MANIFEST) -> None:
        pinned.write_pin(self, path)


def problem(registry: Path = REGISTRY, manifest: Path = MANIFEST) -> str | None:
    """Why the built registry cannot be used as pinned, or None when it can."""
    try:
        pin = Pin.load(manifest)
    except RorError as exc:
        return str(exc)
    return pinned.problem(registry, pin.snapshot_sha256, "ROR", f"the pinned dump {pin.version}")


def _items(fh: IO[str]) -> Iterator[dict[str, Any]]:
    """The objects of a JSON array, read one at a time, so a dump of hundreds of megabytes is
    never held whole."""
    decoder = json.JSONDecoder()
    buffer = ""
    pos = 0
    started = False
    eof = False
    while True:
        # Skip whitespace and separators, reading more when the buffer runs out.
        while True:
            while pos < len(buffer) and buffer[pos] in " \t\r\n,":
                pos += 1
            if pos < len(buffer) or eof:
                break
            chunk = fh.read(1 << 20)
            buffer, pos, eof = buffer[pos:] + chunk, 0, not chunk
        if pos >= len(buffer):
            raise RorError("the dump ends before its array does")
        if not started:
            if buffer[pos] != "[":
                raise RorError("the dump is not a JSON array")
            started, pos = True, pos + 1
            continue
        if buffer[pos] == "]":
            return
        try:
            item, end = decoder.raw_decode(buffer, pos)
        except json.JSONDecodeError:
            if eof or len(buffer) - pos > MAX_RECORD_BYTES:
                raise RorError("the dump holds a record that is not JSON, or too large") from None
            chunk = fh.read(1 << 20)
            buffer, pos, eof = buffer[pos:] + chunk, 0, not chunk
            continue
        if not isinstance(item, dict):
            raise RorError("the dump holds something other than a record")
        yield item
        pos = end


def organisations(archive: Path) -> list[Organisation]:
    """Every organisation in a dump, sorted by identifier. The dump is a zip holding one JSON
    array (and a CSV, which is not read)."""
    try:
        with zipfile.ZipFile(archive) as zf:
            members = [m for m in zf.infolist() if m.filename.endswith(".json")]
            if len(members) != 1:
                raise RorError(f"{archive}: {len(members)} JSON files; expected a ROR dump")
            member = members[0]
            if member.file_size > MAX_JSON_BYTES:
                raise RorError(f"{archive}: {member.filename} is too large to be a ROR dump")
            out: dict[str, Organisation] = {}
            with zf.open(member) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8")
                for item in _items(text):
                    try:
                        org = from_ror_json(item)
                    except (KeyError, TypeError, ValidationError) as exc:
                        raise RorError(f"{archive}: a record cannot be read: {exc}") from None
                    out[org.id] = org
                    if len(out) > MAX_RECORDS:
                        raise RorError(f"{archive}: more than {MAX_RECORDS} records")
    except (zipfile.BadZipFile, OSError, UnicodeDecodeError) as exc:
        raise RorError(f"{archive}: not a readable zip ({exc})") from None
    if not out:
        raise RorError(f"{archive}: no organisations; expected a ROR dump")
    return [out[k] for k in sorted(out)]


def build(archive: Path) -> bytes:
    """The registry's bytes: one organisation document per line, as hashed."""
    return "".join(
        json.dumps(o.document(), sort_keys=True, ensure_ascii=False) + "\n"
        for o in organisations(archive)
    ).encode("utf-8")


def _archive(url: str, sha256: str | None, cache_dir: Path, client: httpx.Client | None) -> Path:
    """The dump at `url`, from the cache when it holds the pinned bytes (`pinned.Downloader`)."""
    name = url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    if name == "content":  # Zenodo's API serves a file at .../files/<name>/content
        name = url.split("?", 1)[0].rstrip("/").rsplit("/", 2)[-2]
    return DOWNLOAD.archive(url, sha256, cache_dir / name, client)


@dataclass(frozen=True)
class Latest:
    """The newest dump ROR has published."""

    version: str
    url: str
    doi: str


def latest(client: httpx.Client | None = None) -> Latest:
    """The newest ROR dump on Zenodo: its version (such as v2.15), file URL and DOI."""
    http, own = DOWNLOAD.client(client)
    try:
        resp = http.get(f"{ZENODO_RECORDS}/{ZENODO_CONCEPT}/versions/latest")
        if resp.status_code != 200:
            raise RorError(f"Zenodo: HTTP {resp.status_code} for the latest ROR dump")
        record = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RorError(f"Zenodo: {exc}") from None
    finally:
        if own:
            http.close()
    files = [f for f in record.get("files") or [] if str(f.get("key", "")).endswith(".zip")]
    if len(files) != 1:
        raise RorError(f"Zenodo record {record.get('id')}: expected one zip, found {len(files)}")
    key = files[0]["key"]
    found = re.match(r"^(v\d+(?:\.\d+)*)-", key)
    if not found:
        raise RorError(f"Zenodo record {record.get('id')}: cannot read a version from {key!r}")
    return Latest(
        version=found.group(1),
        url=f"https://zenodo.org/records/{record['id']}/files/{key}",
        doi=f"https://doi.org/{record['doi']}" if record.get("doi") else "",
    )


@dataclass(frozen=True)
class Report:
    version: str
    records: int
    downloaded: bool
    pinned: bool


def fetch(
    *,
    update_pin: bool = False,
    cache_dir: Path = ARCHIVES,
    registry: Path = REGISTRY,
    manifest: Path = MANIFEST,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> Report:
    """Build the registry from the pinned dump, or, with `update_pin`, pin the newest dump and
    build from that."""
    if not update_pin:
        pin = Pin.load(manifest)
        if problem(registry, manifest) is None:
            return Report(pin.version, pin.records, downloaded=False, pinned=False)
        data = build(_archive(pin.archive, pin.archive_sha256, cache_dir, client))
        if hashlib.sha256(data).hexdigest() != pin.snapshot_sha256:
            raise RorError(
                f"the registry built from ROR dump {pin.version} does not match the pin. If "
                f"ror.py changed, run `{FETCH_COMMAND} --update-pin` and update both "
                "sources.yaml pins"
            )
        pinned.write_atomic(registry, data)
        return Report(pin.version, pin.records, downloaded=True, pinned=False)

    now = now or datetime.now(UTC)
    newest = latest(client)
    archive = _archive(newest.url, None, cache_dir, client)
    try:
        data = build(archive)
    except RorError:
        archive.unlink(missing_ok=True)
        raise
    pinned.write_atomic(registry, data)
    pin = Pin(
        version=newest.version,
        archive=newest.url,
        archive_sha256=pinned.sha256_file(archive),
        doi=newest.doi,
        records=data.count(b"\n"),
        snapshot_sha256=hashlib.sha256(data).hexdigest(),
        fetched_at=now.isoformat(timespec="seconds"),
    )
    try:
        current: Pin | None = Pin.load(manifest)
    except RorError:
        current = None
    unchanged = pinned.same_pin(current, pin)
    if not unchanged:
        pin.write(manifest)
    return Report(pin.version, pin.records, downloaded=True, pinned=not unchanged)


def main(argv: Sequence[str] | None = None) -> int:
    """Console script `dd-ror`."""
    parser = argparse.ArgumentParser(prog="dd-ror", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch", help="build the registry from the pinned ROR dump")
    f.add_argument("--update-pin", action="store_true", help="pin the newest ROR dump")
    f.add_argument("--cache-dir", type=Path, default=ARCHIVES, help="where dumps are kept")
    sub.add_parser("check", help="exit 1 unless the registry is built as pinned")
    args = parser.parse_args(argv)
    if args.command == "check":
        return pinned.check(problem(), "ROR registry matches its pin")
    try:
        report = fetch(update_pin=args.update_pin, cache_dir=args.cache_dir)
    except RorError as exc:
        sys.stderr.write(f"dd-ror: {exc}\n")
        return 1
    pin = Pin.load()
    state = "pinned and built" if report.pinned else "built" if report.downloaded else "current"
    lines = [f"ROR dump {report.version}: {report.records} organisations, {state}."]
    if report.pinned:
        lines.append(f"snapshot_sha256 {pin.snapshot_sha256}; update both sources.yaml pins.")
    lines.append(f"Cite: {pin.citation}")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


class RorDump:
    """The registry built from the pinned dump (`dd_mcp_pid.ror.RorIndex`), used only when it
    matches its pin."""

    def __init__(self, path: Path = REGISTRY, manifest: Path = MANIFEST) -> None:
        self.path = path
        self.manifest = manifest

    @cached_property
    def _index(self) -> shared.RorIndex:
        if (found := problem(self.path, self.manifest)) is not None:
            raise RegistryUnavailable(found)
        return shared.RorIndex(self.path)

    def snapshot_ref(self) -> SnapshotRef:
        try:
            pin = Pin.load(self.manifest)
        except RorError:
            return SnapshotRef(label=f"{REGISTRY_LABEL}:dump:{self.path.name}")
        return SnapshotRef(label=pin.label, fetched_at=pin.fetched_at)

    def find(self, name: str) -> list[Organisation]:
        try:
            return self._index.find(name)
        except UnavailableError as exc:
            raise RegistryUnavailable(str(exc)) from None

    def get(self, ror_id: str) -> Organisation | None:
        try:
            return self._index.get(ror_id)
        except UnavailableError as exc:
            raise RegistryUnavailable(str(exc)) from None


class RorLive:
    """ROR's REST API (`dd_mcp_pid.ror.RorApi`). Any transport failure raises
    `RegistryUnavailable`; the agent then falls back to the dump and marks it stale."""

    def __init__(self, client: httpx.Client | None = None, now: datetime | None = None) -> None:
        # No retry: a failure falls back to the dump at once (`search.py`).
        http = Http("ROR", headers={"User-Agent": USER_AGENT}, pauses=(), given=client)
        self._api = shared.RorApi(http)
        self._now = now

    def snapshot_ref(self) -> SnapshotRef:
        now = self._now or datetime.now(UTC)
        return SnapshotRef(
            label=f"{REGISTRY_LABEL}:live:{now.date().isoformat()}",
            fetched_at=now.isoformat(timespec="seconds"),
        )

    def find(self, name: str) -> list[Organisation]:
        try:
            return self._api.find(name)
        except UnavailableError as exc:
            raise RegistryUnavailable(str(exc)) from None

    def get(self, ror_id: str) -> Organisation | None:
        try:
            return self._api.get(ror_id)
        except UnavailableError as exc:
            raise RegistryUnavailable(str(exc)) from None

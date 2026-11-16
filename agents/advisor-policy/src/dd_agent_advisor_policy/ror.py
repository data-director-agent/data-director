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

This module does not use the Data Director contract: it is the part of the agent that would be
useful without it (docs/specs/system.md). Moving it to a library of its own, which the Linking
Adviser could share, is TODO(#360). This module and `live.py` are the importers of `httpx`
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
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import cached_property
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import IO, Any, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from dd_agent_advisor_policy.retrieve import RegistryUnavailable, SnapshotRef

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "ror"
MANIFEST = DATA_DIR / "manifest.json"
REGISTRY = DATA_DIR / "registry.jsonl"
ARCHIVES = DATA_DIR / "archives"

ROR_URL = "https://ror.org/"
API_BASE = "https://api.ror.org/v2/organizations"
# The Zenodo concept record under which ROR publishes every dump, newest first.
ZENODO_RECORDS = "https://zenodo.org/api/records"
ZENODO_CONCEPT = "6347574"
CITATION = "Research Organization Registry (ROR) data dump. https://doi.org/10.5281/zenodo.6347574"
LICENCE = "CC0 1.0 (ROR data); see SOURCE.md"
FETCH_COMMAND = "uv run dd-ror fetch"
PREPARE_COMMAND = "uv run dd-sources prepare"
TIMEOUT_S = 120.0
LIVE_TIMEOUT_S = 20.0
# The label of evidence from each copy: the registry, then which copy answered.
REGISTRY_LABEL = "ror"

# Limits on a dump not yet pinned, so a malformed download cannot exhaust memory. The dump of
# 2026-10-20 (v2.15) has 146,716 organisations in 330 MB of JSON, the largest 146 kB.
MAX_JSON_BYTES = 2_000_000_000
MAX_RECORDS = 1_000_000
MAX_RECORD_BYTES = 2_000_000

# A bare ROR identifier: a zero, six characters and two check digits.
ROR_ID = re.compile(r"^(?:https?://ror\.org/)?(0[a-z0-9]{6}[0-9]{2})/?$")
ACTIVE = "active"
FUNDER = "funder"


def _user_agent() -> str:
    """Names the project and where to find it, never a person."""
    try:
        ours = version("data-director-agent-advisor-policy")
    except PackageNotFoundError:
        ours = "unknown"
    return (
        f"data-director-advisor-policy/{ours} "
        "(+https://github.com/data-director-agent/data-director)"
    )


def ror_url(value: str) -> str | None:
    """`value` as a ROR identifier URL (`https://ror.org/0xxxxxxNN`), or None if it is not one."""
    found = ROR_ID.match(value.strip().lower())
    return f"{ROR_URL}{found.group(1)}" if found else None


def normalise(name: str) -> str:
    """A name as it is matched: case-folded, with runs of spaces made one."""
    return " ".join(name.casefold().split())


class Name(BaseModel):
    """One of an organisation's names, with ROR's types for it (label, acronym, alias,
    ror_display) and its language, where ROR gives one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str
    types: list[str] = Field(default_factory=list)
    lang: str | None = None

    @field_validator("types")
    @classmethod
    def _sort(cls, values: list[str]) -> list[str]:
        return sorted(set(values))


class Organisation(BaseModel):
    """An organisation as ROR records it, cut to what identifying it needs. Stored in the
    registry exactly as it is hashed, so the line is the document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    """The ROR identifier, as a URL: what the payload cites."""
    names: list[Name]
    types: list[str] = Field(default_factory=list)
    status: str
    country_codes: list[str] = Field(default_factory=list)
    # Crossref Funder IDs (ROR's `fundref`), and the one ROR prefers, where it names one.
    crossref_funder_ids: list[str] = Field(default_factory=list)
    crossref_funder_preferred: str | None = None
    # The organisations ROR names as this one's parents, by identifier.
    parents: list[str] = Field(default_factory=list)

    @field_validator("types", "country_codes", "crossref_funder_ids", "parents")
    @classmethod
    def _sort(cls, values: list[str]) -> list[str]:
        return sorted(set(values))

    @field_validator("names")
    @classmethod
    def _sort_names(cls, values: list[Name]) -> list[Name]:
        unique = {(n.value, tuple(n.types), n.lang or ""): n for n in values}
        return [unique[k] for k in sorted(unique)]

    def document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @property
    def label(self) -> str:
        """The name ROR displays."""
        for wanted in ("ror_display", "label"):
            for name in self.names:
                if wanted in name.types:
                    return name.value
        return self.names[0].value if self.names else self.id

    def all_names(self) -> list[str]:
        """Every name, display name first, then labels, acronyms and aliases, each once."""
        order = {"ror_display": 0, "label": 1, "acronym": 2, "alias": 3}
        ranked = sorted(
            self.names, key=lambda n: (min((order.get(t, 4) for t in n.types), default=4), n.value)
        )
        out: list[str] = []
        for name in ranked:
            if name.value not in out:
                out.append(name.value)
        return out

    def matches(self, name: str) -> bool:
        wanted = normalise(name)
        return any(normalise(n.value) == wanted for n in self.names)

    @property
    def active(self) -> bool:
        return self.status == ACTIVE


def from_ror_json(item: dict[str, Any]) -> Organisation:
    """An organisation from a ROR v2 record, as the dump and the API both give it."""
    fundref: dict[str, Any] = next(
        (e for e in item.get("external_ids") or [] if e.get("type") == "fundref"), {}
    )
    return Organisation(
        id=item["id"],
        names=[
            Name(value=n["value"], types=n.get("types") or [], lang=n.get("lang"))
            for n in item.get("names") or []
            if n.get("value")
        ],
        types=item.get("types") or [],
        status=item.get("status") or "",
        country_codes=[
            code
            for loc in item.get("locations") or []
            if (code := (loc.get("geonames_details") or {}).get("country_code"))
        ],
        crossref_funder_ids=[str(v) for v in fundref.get("all") or []],
        crossref_funder_preferred=fundref.get("preferred"),
        parents=[r["id"] for r in item.get("relationships") or [] if r.get("type") == "parent"],
    )


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


class RorError(Exception):
    """The registry cannot be built or read as pinned. The message says what to do."""


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
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**data)
        except (OSError, ValueError, TypeError) as exc:
            raise RorError(f"ROR pin {path} cannot be read: {exc}") from None

    def write(self, path: Path = MANIFEST) -> None:
        text = json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n"
        path.write_text(text, encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def problem(registry: Path = REGISTRY, manifest: Path = MANIFEST) -> str | None:
    """Why the built registry cannot be used as pinned, or None when it can."""
    try:
        pin = Pin.load(manifest)
    except RorError as exc:
        return str(exc)
    if not registry.is_file():
        return f"the ROR registry is not built at {registry}; run `{PREPARE_COMMAND}`"
    if _sha256(registry) != pin.snapshot_sha256:
        return (
            f"the ROR registry at {registry} does not match the pinned dump {pin.version}; "
            f"run `{PREPARE_COMMAND}`"
        )
    return None


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


def _client(client: httpx.Client | None, timeout: float) -> tuple[httpx.Client, bool]:
    if client is not None:
        return client, False
    return httpx.Client(
        timeout=timeout, follow_redirects=True, headers={"User-Agent": _user_agent()}
    ), True


def _download(url: str, dest: Path, client: httpx.Client | None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(".part")
    http, own = _client(client, TIMEOUT_S)
    try:
        with http.stream("GET", url) as resp:
            if resp.status_code != 200:
                raise RorError(f"{url}: HTTP {resp.status_code}")
            with partial.open("wb") as fh:
                for chunk in resp.iter_bytes():
                    fh.write(chunk)
    except httpx.HTTPError as exc:
        raise RorError(f"{url}: {exc}") from None
    finally:
        if own:
            http.close()
    partial.replace(dest)


def _archive(url: str, sha256: str | None, cache_dir: Path, client: httpx.Client | None) -> Path:
    """The dump at `url`, from the cache when it holds the pinned bytes. Downloaded at most once
    per pin (Blueprint P14)."""
    name = url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    if name == "content":  # Zenodo's API serves a file at .../files/<name>/content
        name = url.split("?", 1)[0].rstrip("/").rsplit("/", 2)[-2]
    path = cache_dir / name
    if path.is_file() and (
        _sha256(path) == sha256 if sha256 is not None else zipfile.is_zipfile(path)
    ):
        return path
    _download(url, path, client)
    if sha256 is not None and (actual := _sha256(path)) != sha256:
        raise RorError(f"{url} has sha256 {actual}, not the pinned {sha256}")
    return path


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(path)


@dataclass(frozen=True)
class Latest:
    """The newest dump ROR has published."""

    version: str
    url: str
    doi: str


def latest(client: httpx.Client | None = None) -> Latest:
    """The newest ROR dump on Zenodo: its version (such as v2.15), file URL and DOI."""
    http, own = _client(client, TIMEOUT_S)
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
        _write(registry, data)
        return Report(pin.version, pin.records, downloaded=True, pinned=False)

    now = now or datetime.now(UTC)
    newest = latest(client)
    archive = _archive(newest.url, None, cache_dir, client)
    try:
        data = build(archive)
    except RorError:
        archive.unlink(missing_ok=True)
        raise
    _write(registry, data)
    pin = Pin(
        version=newest.version,
        archive=newest.url,
        archive_sha256=_sha256(archive),
        doi=newest.doi,
        records=data.count(b"\n"),
        snapshot_sha256=hashlib.sha256(data).hexdigest(),
        fetched_at=now.isoformat(timespec="seconds"),
    )
    try:
        current: Pin | None = Pin.load(manifest)
    except RorError:
        current = None
    unchanged = current is not None and (
        current.archive,
        current.archive_sha256,
        current.snapshot_sha256,
    ) == (pin.archive, pin.archive_sha256, pin.snapshot_sha256)
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
        found = problem()
        sys.stdout.write((found or "ROR registry matches its pin") + "\n")
        return 1 if found else 0
    try:
        report = fetch(args.update_pin, args.cache_dir)
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
    """The registry built from the pinned dump. Lines are parsed only when a name or an
    identifier picks them out, so the whole registry is never held as objects."""

    def __init__(self, path: Path = REGISTRY, manifest: Path = MANIFEST) -> None:
        self.path = path
        self.manifest = manifest

    @cached_property
    def _lines(self) -> list[str]:
        if (found := problem(self.path, self.manifest)) is not None:
            raise RegistryUnavailable(found)
        with self.path.open(encoding="utf-8") as fh:
            return [line for line in fh if line.strip()]

    @cached_property
    def _index(self) -> tuple[dict[str, list[int]], dict[str, int]]:
        by_name: dict[str, list[int]] = {}
        by_id: dict[str, int] = {}
        for i, line in enumerate(self._lines):
            doc = json.loads(line)
            by_id[doc["id"]] = i
            if doc.get("status") != ACTIVE:
                continue
            for name in {normalise(n["value"]) for n in doc.get("names") or []}:
                by_name.setdefault(name, []).append(i)
        return by_name, by_id

    def _at(self, i: int) -> Organisation:
        return Organisation.model_validate(json.loads(self._lines[i]))

    def snapshot_ref(self) -> SnapshotRef:
        try:
            pin = Pin.load(self.manifest)
        except RorError:
            return SnapshotRef(label=f"{REGISTRY_LABEL}:dump:{self.path.name}")
        return SnapshotRef(label=pin.label, fetched_at=pin.fetched_at)

    def find(self, name: str) -> list[Organisation]:
        by_name, _ = self._index
        return sorted((self._at(i) for i in by_name.get(normalise(name), [])), key=lambda o: o.id)

    def get(self, ror_id: str) -> Organisation | None:
        url = ror_url(ror_id)
        _, by_id = self._index
        return self._at(by_id[url]) if url and url in by_id else None


class RorLive:
    """ROR's REST API. Any transport failure raises `RegistryUnavailable`; the agent then falls
    back to the dump and marks it stale."""

    def __init__(self, client: httpx.Client | None = None, now: datetime | None = None) -> None:
        self._client = client
        self._now = now

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=LIVE_TIMEOUT_S, headers={"User-Agent": _user_agent()}
            )
        return self._client

    def _get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        try:
            return self._http().get(url, params=params)
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"ROR: {exc}") from None

    def snapshot_ref(self) -> SnapshotRef:
        now = self._now or datetime.now(UTC)
        return SnapshotRef(
            label=f"{REGISTRY_LABEL}:live:{now.date().isoformat()}",
            fetched_at=now.isoformat(timespec="seconds"),
        )

    def find(self, name: str) -> list[Organisation]:
        resp = self._get(API_BASE, {"query": name})
        if resp.status_code != 200:
            raise RegistryUnavailable(f"ROR: HTTP {resp.status_code} for a search")
        try:
            items = resp.json().get("items") or []
            found = [from_ror_json(item) for item in items]
        except (ValueError, KeyError, TypeError, AttributeError, ValidationError) as exc:
            raise RegistryUnavailable(f"ROR: an answer that cannot be read ({exc})") from None
        unique = {o.id: o for o in found if o.active and o.matches(name)}
        return [unique[k] for k in sorted(unique)]

    def get(self, ror_id: str) -> Organisation | None:
        url = ror_url(ror_id)
        if url is None:
            return None
        resp = self._get(f"{API_BASE}/{url.removeprefix(ROR_URL)}")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise RegistryUnavailable(f"ROR: HTTP {resp.status_code} for {url}")
        try:
            return from_ror_json(resp.json())
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            raise RegistryUnavailable(f"ROR: an answer that cannot be read ({exc})") from None

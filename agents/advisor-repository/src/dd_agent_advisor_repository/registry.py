"""The whole of re3data, from one monthly export pinned by URL and SHA-256.

re3data publishes every online repository's record as a zip of XML files in metadata schema 4.0
(https://www.re3data.org/data), and keeps one archive per month. `manifest.json` beside this
package's data pins one archive and the JSON Lines built from it:

- `archive`, `archive_sha256`: the export, as re3data serves it;
- `snapshot_sha256`: `registry.jsonl`, one trimmed record per line in the form that is hashed
  (`records.py`), sorted by identifier. The same archive and parser always build the same bytes,
  so both `sources.yaml` files pin this hash, and the harness's source check verifies every
  re3data evidence item against it (docs/specs/grounding.md).

Neither the archive nor `registry.jsonl` is committed. `dd-re3data fetch` downloads the pinned
archive once (or uses the copy in its cache), verifies it and builds the registry. With
`--update-pin` it pins another month instead, which the monthly refresh does.

re3data's records are CC0. We credit re3data nonetheless: `CITATION` is the service's own
citation, written into the manifest and repeated in every statement the agent makes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import httpx

from dd_agent_advisor_repository.records import Re3dataRecord, from_re3data_xml

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "re3data"
MANIFEST = DATA_DIR / "manifest.json"
REGISTRY = DATA_DIR / "registry.jsonl"
ARCHIVES = DATA_DIR / "archives"

EXPORT_URL = "https://www.re3data.org/export/re3data-repositories-{month}.zip"
CITATION = "re3data.org - Registry of Research Data Repositories. https://doi.org/10.17616/R3D"
SCHEMA_CITATION = (
    "re3data.org Metadata Schema for the Description of Research Data Repositories, "
    "version 4.0. https://doi.org/10.48440/re3.014"
)
LICENCE = "CC0 1.0 (re3data metadata); see SOURCE.md"
SCHEMA = "4.0"
FETCH_COMMAND = "uv run dd-re3data fetch"
TIMEOUT_S = 120.0

# Limits on an archive not yet pinned, so a malformed download cannot exhaust memory. The export
# of 2026-11 has 3,540 members, the largest 41 kB.
MAX_MEMBERS = 50_000
MAX_MEMBER_BYTES = 2_000_000


def _user_agent() -> str:
    """Names the project and where to find it, never a person (re3data asks nothing more)."""
    try:
        ours = version("data-director-agent-advisor-repository")
    except PackageNotFoundError:
        ours = "unknown"
    return (
        f"data-director-advisor-repository/{ours} "
        "(+https://github.com/data-director-agent/data-director)"
    )


class RegistryError(Exception):
    """The registry cannot be built or read as pinned. The message says what to do."""


@dataclass(frozen=True)
class Pin:
    month: str
    archive: str
    archive_sha256: str
    records: int
    snapshot_sha256: str
    fetched_at: str
    schema: str = SCHEMA
    citation: str = CITATION
    schema_citation: str = SCHEMA_CITATION
    licence: str = LICENCE

    @property
    def label(self) -> str:
        """The evidence's `snapshot_ref` for records from this export."""
        return f"re3data:export:{self.month}"

    @property
    def credit(self) -> str:
        """The sentence that credits re3data in a statement."""
        return (
            f"Repository details are from re3data.org, the Registry of Research Data "
            f"Repositories (export of {self.month}, CC0; https://doi.org/10.17616/R3D)."
        )

    @classmethod
    def load(cls, path: Path = MANIFEST) -> Pin:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**data)
        except (OSError, ValueError, TypeError) as exc:
            raise RegistryError(f"re3data pin {path} cannot be read: {exc}") from None

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
    except RegistryError as exc:
        return str(exc)
    if not registry.is_file():
        return f"the re3data registry is not built at {registry}; run `{FETCH_COMMAND}`"
    if _sha256(registry) != pin.snapshot_sha256:
        return (
            f"the re3data registry at {registry} does not match the pinned export of "
            f"{pin.month}; run `{FETCH_COMMAND}`"
        )
    return None


def records(archive: Path) -> list[Re3dataRecord]:
    """Every repository in an export, sorted by identifier."""
    try:
        with zipfile.ZipFile(archive) as zf:
            members = [m for m in zf.infolist() if m.filename.endswith(".xml")]
            if not members or len(members) > MAX_MEMBERS:
                raise RegistryError(f"{archive}: {len(members)} XML records; expected an export")
            out: dict[str, Re3dataRecord] = {}
            for member in members:
                if member.file_size > MAX_MEMBER_BYTES:
                    raise RegistryError(f"{archive}: {member.filename} is too large to be a record")
                record = from_re3data_xml(zf.read(member))
                if record is not None:
                    out[record.re3data_id] = record
    except (zipfile.BadZipFile, OSError) as exc:
        raise RegistryError(f"{archive}: not a readable zip ({exc})") from None
    return [out[k] for k in sorted(out)]


def build(archive: Path) -> bytes:
    """The registry's bytes: one record document per line, as hashed (`records.py`)."""
    return "".join(
        json.dumps(r.document(), sort_keys=True, ensure_ascii=False) + "\n"
        for r in records(archive)
    ).encode("utf-8")


def _ids(registry: Path) -> set[str]:
    if not registry.is_file():
        return set()
    with registry.open(encoding="utf-8") as fh:
        return {json.loads(line)["re3data_id"] for line in fh if line.strip()}


def _download(url: str, dest: Path, client: httpx.Client | None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(".part")
    own = client is None
    client = client or httpx.Client(
        timeout=TIMEOUT_S, follow_redirects=True, headers={"User-Agent": _user_agent()}
    )
    try:
        with client.stream("GET", url) as resp:
            if resp.status_code != 200:
                raise RegistryError(f"{url}: HTTP {resp.status_code}")
            with partial.open("wb") as fh:
                for chunk in resp.iter_bytes():
                    fh.write(chunk)
    except httpx.HTTPError as exc:
        raise RegistryError(f"{url}: {exc}") from None
    finally:
        if own:
            client.close()
    partial.replace(dest)


def _archive(url: str, sha256: str | None, cache_dir: Path, client: httpx.Client | None) -> Path:
    """The archive at `url`, from the cache when it holds the pinned bytes. Downloaded at most
    once per pin (Blueprint P14)."""
    path = cache_dir / url.rsplit("/", 1)[-1]
    # A monthly archive does not change once published, so a whole copy (downloads are renamed
    # into place only when complete) is reused when no pin says otherwise.
    if path.is_file() and (sha256 is None or _sha256(path) == sha256):
        return path
    _download(url, path, client)
    if sha256 is not None and (actual := _sha256(path)) != sha256:
        raise RegistryError(f"{url} has sha256 {actual}, not the pinned {sha256}")
    return path


def _write(path: Path, data: bytes) -> None:
    partial = path.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(path)


@dataclass(frozen=True)
class Report:
    month: str
    records: int
    added: list[str]
    removed: list[str]
    downloaded: bool
    pinned: bool


def fetch(
    month: str | None = None,
    update_pin: bool = False,
    cache_dir: Path = ARCHIVES,
    registry: Path = REGISTRY,
    manifest: Path = MANIFEST,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> Report:
    """Build the registry from the pinned export, or, with `update_pin`, pin `month`'s export
    (the current month by default) and build from that."""
    before = _ids(registry)
    if not update_pin:
        if month is not None:
            raise RegistryError("--month needs --update-pin; without it the pinned month is built")
        pin = Pin.load(manifest)
        if problem(registry, manifest) is None:
            return Report(pin.month, pin.records, [], [], downloaded=False, pinned=False)
        data = build(_archive(pin.archive, pin.archive_sha256, cache_dir, client))
        if hashlib.sha256(data).hexdigest() != pin.snapshot_sha256:
            raise RegistryError(
                f"the registry built from the export of {pin.month} does not match the pin. If "
                f"records.py changed, run `{FETCH_COMMAND} --update-pin --month {pin.month}` "
                "and update both sources.yaml pins"
            )
        _write(registry, data)
        return Report(pin.month, pin.records, [], [], downloaded=True, pinned=False)

    now = now or datetime.now(UTC)
    month = month or now.strftime("%Y-%m")
    url = EXPORT_URL.format(month=month)
    archive = _archive(url, None, cache_dir, client)
    data = build(archive)
    _write(registry, data)
    after = _ids(registry)
    pin = Pin(
        month=month,
        archive=url,
        archive_sha256=_sha256(archive),
        records=len(after),
        snapshot_sha256=hashlib.sha256(data).hexdigest(),
        fetched_at=now.isoformat(timespec="seconds"),
    )
    try:
        current: Pin | None = Pin.load(manifest)
    except RegistryError:
        current = None
    # The same export built to the same bytes is already pinned; keep its date, so that pinning
    # it again changes nothing.
    unchanged = current is not None and (
        current.archive,
        current.archive_sha256,
        current.snapshot_sha256,
    ) == (pin.archive, pin.archive_sha256, pin.snapshot_sha256)
    if not unchanged:
        pin.write(manifest)
    return Report(
        month,
        len(after),
        sorted(after - before) if before else [],
        sorted(before - after),
        downloaded=True,
        pinned=not unchanged,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Console script `dd-re3data`."""
    parser = argparse.ArgumentParser(prog="dd-re3data", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch", help="build the registry from the pinned re3data export")
    f.add_argument("--update-pin", action="store_true", help="pin another month's export")
    f.add_argument("--month", help="YYYY-MM, with --update-pin (default: this month)")
    f.add_argument("--cache-dir", type=Path, default=ARCHIVES, help="where archives are kept")
    f.add_argument("--summary", type=Path, help="write the report as JSON to this file")
    sub.add_parser("check", help="exit 1 unless the registry is built as pinned")
    args = parser.parse_args(argv)
    if args.command == "check":
        found = problem()
        sys.stdout.write((found or "re3data registry matches its pin") + "\n")
        return 1 if found else 0
    try:
        report = fetch(args.month, args.update_pin, args.cache_dir)
    except RegistryError as exc:
        sys.stderr.write(f"dd-re3data: {exc}\n")
        return 1
    if args.summary:
        args.summary.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")
    pin = Pin.load()
    state = "pinned and built" if report.pinned else "built" if report.downloaded else "current"
    lines = [f"re3data export of {report.month}: {report.records} repositories, {state}."]
    if report.pinned:
        lines.append(f"snapshot_sha256 {pin.snapshot_sha256}; update both sources.yaml pins.")
    lines.append(f"Cite: {pin.citation}")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0

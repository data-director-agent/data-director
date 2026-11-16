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
`--update-pin` it pins another month instead, which the monthly refresh does. `SOURCE` declares
the registry to `dd-sources prepare` (dd_sdk.sources), which is how setup, CI and deployment
build it.

re3data's records are CC0. We credit re3data nonetheless: `CITATION` is the service's own
citation, written into the manifest and repeated in every statement the agent makes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import ValidationError

from dd_agent_advisor_repository.records import Re3dataRecord, from_re3data_xml
from dd_sdk.registry import pinned
from dd_sdk.sources import BuiltSource, SourceBuildError

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
    return pinned.user_agent(
        "data-director-agent-advisor-repository", "data-director-advisor-repository"
    )


class RegistryError(pinned.PinError):
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
        return pinned.read_pin(cls, path, "re3data", RegistryError)

    def write(self, path: Path = MANIFEST) -> None:
        pinned.write_pin(self, path)


def problem(registry: Path = REGISTRY, manifest: Path = MANIFEST) -> str | None:
    """Why the built registry cannot be used as pinned, or None when it can."""
    try:
        pin = Pin.load(manifest)
    except RegistryError as exc:
        return str(exc)
    return pinned.problem(
        registry, pin.snapshot_sha256, "re3data", f"the pinned export of {pin.month}"
    )


def _is_record(name: str) -> bool:
    """Whether a member holds a record: an XML file, and not one of the `__MACOSX/` or `._*`
    resource-fork entries an archive made on macOS carries beside each file."""
    base = name.rsplit("/", 1)[-1]
    return name.endswith(".xml") and not name.startswith("__MACOSX/") and not base.startswith("._")


def records(archive: Path) -> list[Re3dataRecord]:
    """Every repository in an export, sorted by identifier. A member that cannot be read as a
    record is an error naming it, not a traceback."""
    try:
        with zipfile.ZipFile(archive) as zf:
            members = [m for m in zf.infolist() if _is_record(m.filename)]
            if not members or len(members) > MAX_MEMBERS:
                raise RegistryError(f"{archive}: {len(members)} XML records; expected an export")
            out: dict[str, Re3dataRecord] = {}
            for member in members:
                if member.file_size > MAX_MEMBER_BYTES:
                    raise RegistryError(f"{archive}: {member.filename} is too large to be a record")
                try:
                    record = from_re3data_xml(zf.read(member))
                except (ET.ParseError, ValidationError) as exc:
                    raise RegistryError(f"{archive}: {member.filename}: {exc}") from None
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


def _ids(data: bytes) -> set[str]:
    """The identifiers in a registry's bytes. Empty when they cannot be read: a corrupt registry
    is about to be rebuilt, and only the report of what was added is lost."""
    try:
        return {
            json.loads(line)["re3data_id"]
            for line in data.decode("utf-8").splitlines()
            if line.strip()
        }
    except json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError:
        return set()


def _archive(url: str, sha256: str | None, cache_dir: Path, client: httpx.Client | None) -> Path:
    """The archive at `url`, from the cache when it holds the pinned bytes (`pinned.Downloader`).
    A monthly archive does not change once published."""
    downloader = pinned.Downloader(_user_agent(), TIMEOUT_S, RegistryError)
    return downloader.archive(url, sha256, cache_dir / url.rsplit("/", 1)[-1], client)


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
        pinned.write_atomic(registry, data)
        return Report(pin.month, pin.records, [], [], downloaded=True, pinned=False)

    now = now or datetime.now(UTC)
    month = month or now.strftime("%Y-%m")
    url = EXPORT_URL.format(month=month)
    archive = _archive(url, None, cache_dir, client)
    try:
        data = build(archive)
    except RegistryError:
        # Not the export after all; the next run downloads it again rather than reusing this.
        archive.unlink(missing_ok=True)
        raise
    before = _ids(registry.read_bytes()) if registry.is_file() else set()
    pinned.write_atomic(registry, data)
    after = _ids(data)
    pin = Pin(
        month=month,
        archive=url,
        archive_sha256=pinned.sha256_file(archive),
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
    unchanged = pinned.same_pin(current, pin)
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
        return pinned.check(problem(), "re3data registry matches its pin")
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


def _prepare(cache_dir: Path | None) -> None:
    try:
        fetch(cache_dir=cache_dir or ARCHIVES)
    except RegistryError as exc:
        raise SourceBuildError(f"re3data: {exc}") from None


def _pin() -> str:
    try:
        return Pin.load().archive_sha256
    except RegistryError as exc:
        raise SourceBuildError(str(exc)) from None


# Registered under the `dd.sources` entry point (pyproject.toml), so `dd-sources prepare` builds
# the registry without anything else knowing how.
SOURCE = BuiltSource(name="re3data", pin=_pin, problem=lambda: problem(), prepare=_prepare)

"""The pinned OpenAlex snapshot, and `dd-journals fetch`, which builds the registry from it.

`data/manifest.json` pins one quarterly OpenAlex snapshot: the URL, size and SHA-256 of each part
of its Sources entity, and the SHA-256 of the `journals.jsonl` they build. OpenAlex's own snapshot
manifest gives sizes but no hashes, so the hashes are taken when the snapshot is pinned. Neither
the parts nor `journals.jsonl` is committed: `dd-journals fetch` downloads the parts once into
`data/archives/` (or the cache it is given), checks each against the pin, builds the registry and
checks it too. `dd-journals fetch --update-pin` pins the newest snapshot instead.

Only OpenAlex's public bucket is asked, over HTTPS; nothing about the person or the deployment is
sent but a User-Agent naming this library.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import IO, Any

from dd_journals.build import build
from dd_journals.registry import PinError, Registry

DATA_DIR = Path(__file__).resolve().parent / "data"
MANIFEST = DATA_DIR / "manifest.json"
REGISTRY = DATA_DIR / "journals.jsonl"
ARCHIVES = DATA_DIR / "archives"

BUCKET = "https://openalex.s3.amazonaws.com/"
SNAPSHOT_MANIFEST = f"{BUCKET}data/jsonl/manifest.json"
ENTITY = "sources"
SOURCE = "OpenAlex snapshot, Sources entity"
CITATION = (
    "Priem, J., Piwowar, H., & Orr, R. (2022). OpenAlex: A fully-open index of scholarly works, "
    "authors, venues, institutions, and concepts. https://doi.org/10.48550/arXiv.2205.01833"
)
LICENCE = "CC0 1.0 (OpenAlex data); see SOURCE.md"
USER_AGENT = "data-director-journals/0.1 (+https://github.com/data-director-agent/data-director)"
TIMEOUT_S = 120.0
CHUNK = 1 << 20

Opener = Callable[[str], IO[bytes]]


def _urlopen(url: str) -> IO[bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    response: IO[bytes] = urllib.request.urlopen(request, timeout=TIMEOUT_S)
    return response


def https_url(url: str) -> str:
    """An `s3://openalex/...` URL from OpenAlex's manifest as the public HTTPS URL."""
    prefix = "s3://openalex/"
    if not url.startswith(prefix):
        raise PinError(f"{url}: not a part of the OpenAlex bucket")
    return BUCKET + url.removeprefix(prefix)


@dataclass(frozen=True)
class Part:
    url: str
    content_length: int
    record_count: int
    sha256: str

    @property
    def cache_name(self) -> str:
        """The part's file name in the cache: its path in the bucket, flattened."""
        return self.url.removeprefix(BUCKET).replace("/", "_")


@dataclass(frozen=True)
class Pin:
    snapshot_date: str
    parts: tuple[Part, ...]
    journals: int
    registry_sha256: str
    fetched_at: str
    snapshot_manifest: str = SNAPSHOT_MANIFEST
    source: str = SOURCE
    citation: str = CITATION
    licence: str = LICENCE

    @property
    def label(self) -> str:
        """The snapshot as answers name it."""
        return f"openalex:sources:{self.snapshot_date}"

    @classmethod
    def load(cls, path: Path = MANIFEST) -> Pin:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**{**data, "parts": tuple(Part(**p) for p in data["parts"])})
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise PinError(f"{path}: cannot read the pin ({exc})") from None

    def save(self, path: Path = MANIFEST) -> None:
        data = asdict(self)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path, opener: Opener, sha256: str | None = None) -> str:
    """Download `url` to `target` unless a copy with `sha256` is there already; the SHA-256 of
    what is there afterwards. A download that does not match `sha256` is removed."""
    if sha256 is not None and target.exists() and _sha256(target) == sha256:
        return sha256
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    try:
        with opener(url) as response, partial.open("wb") as out:
            while chunk := response.read(CHUNK):
                out.write(chunk)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise PinError(f"{url}: cannot download ({exc})") from None
    got = _sha256(partial)
    if sha256 is not None and got != sha256:
        partial.unlink()
        raise PinError(f"{url}: does not match its pin; run `dd-journals fetch --update-pin`")
    partial.replace(target)
    return got


def _write(registry: Path, data: bytes) -> None:
    registry.parent.mkdir(parents=True, exist_ok=True)
    partial = registry.with_name(registry.name + ".part")
    partial.write_bytes(data)
    partial.replace(registry)


def fetch(
    cache_dir: Path = ARCHIVES,
    registry: Path = REGISTRY,
    manifest: Path = MANIFEST,
    opener: Opener = _urlopen,
) -> Pin:
    """Build `registry` from the pinned parts, downloading those not in `cache_dir`."""
    pin = Pin.load(manifest)
    paths = []
    for part in pin.parts:
        target = cache_dir / part.cache_name
        download(part.url, target, opener, part.sha256)
        paths.append(target)
    data, _ = build(paths)
    if hashlib.sha256(data).hexdigest() != pin.registry_sha256:
        raise PinError(
            "the parts match their pin but build a different registry: dd_journals.build changed, "
            "so run `dd-journals fetch --update-pin`"
        )
    _write(registry, data)
    return pin


def _sources_files(opener: Opener) -> tuple[str, list[dict[str, Any]]]:
    try:
        with opener(SNAPSHOT_MANIFEST) as response:
            snapshot = json.loads(response.read())
        entity = next(e for e in snapshot["entities"] if e["entity"] == ENTITY)
        return str(snapshot["date"]), list(entity["files"])
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        raise PinError(f"{SNAPSHOT_MANIFEST}: cannot read OpenAlex's manifest ({exc})") from None


def update_pin(
    cache_dir: Path = ARCHIVES,
    registry: Path = REGISTRY,
    manifest: Path = MANIFEST,
    opener: Opener = _urlopen,
) -> Pin:
    """Pin OpenAlex's newest snapshot: download every part, hash it, build the registry and write
    the pin."""
    date, files = _sources_files(opener)
    parts, paths = [], []
    for item in files:
        url = https_url(str(item["url"]))
        meta = item.get("meta") or {}
        part = Part(url, int(meta.get("content_length", 0)), int(meta.get("record_count", 0)), "")
        target = cache_dir / part.cache_name
        parts.append(Part(**{**asdict(part), "sha256": download(url, target, opener)}))
        paths.append(target)
    data, count = build(paths)
    _write(registry, data)
    pin = Pin(
        snapshot_date=date,
        parts=tuple(sorted(parts, key=lambda p: p.url)),
        journals=count,
        registry_sha256=hashlib.sha256(data).hexdigest(),
        fetched_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
    )
    pin.save(manifest)
    return pin


def problem(registry: Path = REGISTRY, manifest: Path = MANIFEST) -> str | None:
    """Why the registry is not built as pinned, or None when it is."""
    try:
        pin = Pin.load(manifest)
    except PinError as exc:
        return str(exc)
    if not registry.exists():
        return f"{registry} is not built: run `dd-journals fetch`"
    if _sha256(registry) != pin.registry_sha256:
        return f"{registry} does not match its pin: run `dd-journals fetch`"
    return None


@cache
def registry() -> Registry:
    """The built registry, checked against its pin."""
    return Registry.load(REGISTRY, Pin.load().registry_sha256)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dd-journals", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch", help="build the registry from the pinned snapshot")
    f.add_argument("--cache-dir", type=Path, default=ARCHIVES, help="where downloads are kept")
    f.add_argument("--update-pin", action="store_true", help="pin OpenAlex's newest snapshot")
    sub.add_parser("check", help="say whether the registry is built as pinned")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            if message := problem():
                sys.stderr.write(f"dd-journals: {message}\n")
                return 1
            sys.stdout.write(f"{REGISTRY} is built as pinned ({Pin.load().label})\n")
            return 0
        step = update_pin if args.update_pin else fetch
        pin = step(cache_dir=args.cache_dir)
    except PinError as exc:
        sys.stderr.write(f"dd-journals: {exc}\n")
        return 1
    built = os.path.relpath(REGISTRY)
    sys.stdout.write(f"built {pin.journals} journals from {pin.label} into {built}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

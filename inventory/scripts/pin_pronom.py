# /// script
# requires-python = ">=3.14"
# dependencies = ["opf-fido==1.6.1"]
# ///
"""Pin a PRONOM release as the signatures `dd_inventory.identify` gives fido.

fido 1.6.1 ships PRONOM v109 (2022), and its update service stops there, so this builds a fido
signature file from a current release and writes it, with PRONOM's container signatures and a
manifest of hashes, to `src/dd_inventory/pronom/`:

    uv run inventory/scripts/pin_pronom.py --version 125 --container 20260907

Run it after each PRONOM release (about every two months; https://pronom.nationalarchives.gov.uk/
lists them, and its signature list names the latest container file), then commit the output.

1. The DROID signature file of the release gives the set of PRONOM identifiers (PUIDs).
2. Each PUID's PRONOM XML record is fetched, and fido's own converter (`fido.prepare`) turns the
   records into fido's format file, as fido's maintainers built the files it ships.
3. The converted PUIDs are checked against the DROID file's: any missing, and any fido could not
   convert, are listed in the manifest.

The per-format records are PRONOM's current ones, not a frozen copy of the release, so run this
soon after a release: the manifest lists every record updated after the release was created.
fido's converter also downloads each record's reference files to checksum them; this script
stops it, since identification never reads them, and contacts only The National Archives.

PRONOM is under the Open Government Licence v3.0 (`src/dd_inventory/pronom/LICENCE.md`).
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import io
import json
import sys
import tempfile
import time
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from xml.etree import ElementTree

from fido import prepare

OUT = Path(__file__).resolve().parents[1] / "src" / "dd_inventory" / "pronom"
DROID_URL = "https://cdn.nationalarchives.gov.uk/documents/DROID_SignatureFile_V{version}.xml"
RECORD_URL = "https://www.nationalarchives.gov.uk/pronom/{puid}.xml"
CONTAINER_URL = (
    "https://pronom.nationalarchives.gov.uk/container-signatures/container-signature-{date}.xml"
)
DROID_NS = {"d": "http://www.nationalarchives.gov.uk/pronom/SignatureFile"}
HEADERS = {"User-Agent": "data-director-inventory pin_pronom.py"}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return bytes(response.read())
        except HTTPError:
            raise
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def release_puids(droid: bytes, version: int) -> tuple[list[str], str]:
    root = ElementTree.fromstring(droid)
    if root.get("Version") != str(version):
        sys.exit(f"the DROID file is version {root.get('Version')}, not {version}")
    puids = [
        f.get("PUID", "") for f in root.iterfind("d:FileFormatCollection/d:FileFormat", DROID_NS)
    ]
    return sorted(p for p in puids if p), root.get("DateCreated", "")


def fetch_records(puids: list[str], throttle: float) -> tuple[bytes, list[str]]:
    """Every PUID's record in one zip, as fido's converter reads them; and those PRONOM lacks."""
    buffer, missing = io.BytesIO(), []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as records:
        for n, puid in enumerate(puids, 1):
            try:
                records.writestr(
                    puid.replace("/", "-") + ".xml", fetch(RECORD_URL.format(puid=puid))
                )
            except HTTPError as exc:
                print(f"{puid}: HTTP {exc.code}", file=sys.stderr)
                missing.append(puid)
            if n % 250 == 0:
                print(f"{n}/{len(puids)} records", file=sys.stderr)
            time.sleep(throttle)
    return buffer.getvalue(), missing


def _no_reference_files(url: str, *_args: object, **_kwargs: object) -> None:
    raise HTTPError(url, 404, "reference files are not fetched", None, None)  # type: ignore[arg-type]


def convert(records: bytes) -> tuple[bytes, list[str]]:
    """fido's format file from the records, and the PUIDs whose signatures fido could not take."""
    prepare.urlopen = _no_reference_files  # type: ignore[attr-defined]
    notices = io.StringIO()
    info = prepare.FormatInfo(io.BytesIO(records))
    with contextlib.redirect_stderr(notices):
        info.load_pronom_xml()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "formats.xml"
        info.save(str(out))
        xml = out.read_bytes()
    skipped = sorted(
        {
            line.split("puid ")[1].split()[0]
            for line in notices.getvalue().splitlines()
            if "incompatible" in line
        }
    )
    return xml, skipped


def updated_since(xml: bytes, created: str) -> list[str]:
    """The PUIDs whose record was updated after the release was created."""
    cutoff = datetime.fromisoformat(created).date()
    later = []
    for fmt in ElementTree.fromstring(xml).iterfind("format"):
        modified = fmt.findtext("details/record_metadata/{http://purl.org/dc/terms/}modified") or ""
        with contextlib.suppress(ValueError):
            if datetime.strptime(modified.strip(), "%d %b %Y").replace(tzinfo=UTC).date() > cutoff:
                later.append(fmt.findtext("puid") or "")
    return sorted(later)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--version", type=int, required=True, help="PRONOM release, e.g. 125")
    parser.add_argument("--container", required=True, help="container file date, e.g. 20260907")
    parser.add_argument("--throttle", type=float, default=0.25, help="seconds between records")
    args = parser.parse_args()

    droid_url = DROID_URL.format(version=args.version)
    droid = fetch(droid_url)
    puids, created = release_puids(droid, args.version)
    print(f"PRONOM v{args.version}: {len(puids)} formats", file=sys.stderr)
    records, missing = fetch_records(puids, args.throttle)
    xml, skipped = convert(records)
    converted = {fmt.findtext("puid") for fmt in ElementTree.fromstring(xml).iterfind("format")}
    unconverted = sorted(set(puids) - converted - set(missing))
    container_url = CONTAINER_URL.format(date=args.container)
    container = fetch(container_url)

    formats_name = f"formats-v{args.version}.xml.gz"
    container_name = f"container-signature-{args.container}.xml"
    # A fixed mtime and no file name in the header, so the same records give the same bytes.
    formats = gzip.compress(xml, compresslevel=9, mtime=0)
    for old in OUT.glob("formats-v*.xml.gz"):
        old.unlink()
    for old in OUT.glob("container-signature-*.xml"):
        old.unlink()
    (OUT / formats_name).write_bytes(formats)
    (OUT / container_name).write_bytes(container)
    manifest = {
        "pronom_version": args.version,
        "release_created": created,
        "droid_signature_file": {"url": droid_url, "sha256": sha256(droid)},
        "record_url": RECORD_URL,
        "retrieved": datetime.now(UTC).date().isoformat(),
        "converted_with": "opf-fido 1.6.1 (fido.prepare), reference files not fetched",
        "formats": {"file": formats_name, "sha256": sha256(formats), "count": len(converted)},
        "container": {
            "file": container_name,
            "date": datetime.strptime(args.container, "%Y%m%d")
            .replace(tzinfo=UTC)
            .date()
            .isoformat(),
            "url": container_url,
            "sha256": sha256(container),
        },
        "records_missing": missing,
        "records_not_converted": unconverted,
        "signatures_not_converted": skipped,
        "records_updated_after_release": updated_since(xml, created),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {formats_name} ({len(formats)} bytes), {container_name}, manifest.json",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()

# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Pin a PRONOM release's format records as the data `dd_formats` describes formats from.

Reads a fido format file of one PRONOM release (the one `dd-inventory` identifies against, built
by `inventory/scripts/pin_pronom.py`) and writes one JSON record per PRONOM identifier (PUID),
with a manifest, to `src/dd_formats/data/`:

    uv run --no-project --python 3.14 formats/scripts/pin_pronom_records.py \\
        inventory/src/dd_inventory/pronom/formats-v125.xml.gz --version 125 \\
        --release-created 2026-09-02

Run it after each PRONOM release that `dd-inventory` is pinned to, then commit the output. Each
record keeps what describes a format (name, version, media types, extensions) and, for a
deprecated PUID, the PUID that replaces it; PRONOM's descriptions and signatures are left out.
The output is reproducible: the same input gives the same bytes.

PRONOM is under the Open Government Licence v3.0 (`src/dd_formats/data/LICENCE.md`).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree

OUT = Path(__file__).resolve().parents[1] / "src" / "dd_formats" / "data"
PAGE_URL = "https://www.nationalarchives.gov.uk/PRONOM/{puid}"
DC = "{http://purl.org/dc/elements/1.1/}"
# PRONOM marks a retired PUID in its description: "PUID deprecated. Please see fmt/353 ...".
DEPRECATED = re.compile(r"PUID deprecated\.\s*Please see ((?:x-)?fmt/\d+)", re.IGNORECASE)


def _texts(element: ElementTree.Element, tag: str) -> list[str]:
    return sorted({t.strip() for e in element.findall(tag) if (t := e.text) and t.strip()})


def record(element: ElementTree.Element) -> dict[str, object]:
    """One fido `<format>` as a dd_formats record."""
    puid = (element.findtext("puid") or "").strip()
    description = element.findtext(f"details/{DC}description") or ""
    replaced = DEPRECATED.search(description)
    # A record that names itself (fmt/60 in v125) names no replacement.
    superseded_by = replaced.group(1) if replaced and replaced.group(1) != puid else None
    return {
        "puid": puid,
        "name": (element.findtext("name") or "").strip(),
        "version": (element.findtext("version") or "").strip() or None,
        "media_types": _texts(element, "mime"),
        "extensions": sorted({e.lower() for e in _texts(element, "extension")}),
        "superseded_by": superseded_by,
        "url": PAGE_URL.format(puid=puid),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("formats", type=Path, help="fido format file (.xml or .xml.gz)")
    parser.add_argument("--version", type=int, required=True, help="PRONOM release, e.g. 125")
    parser.add_argument("--release-created", required=True, help="the release's date, ISO 8601")
    args = parser.parse_args()

    raw = args.formats.read_bytes()
    xml = gzip.decompress(raw) if args.formats.suffix == ".gz" else raw
    root = ElementTree.fromstring(xml)
    records = sorted((record(f) for f in root.findall("format")), key=lambda r: str(r["puid"]))
    lines = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records)
    data = lines.encode("utf-8")
    name = f"pronom-v{args.version}.jsonl"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_bytes(data)
    manifest = {
        "pronom_version": args.version,
        "release_created": args.release_created,
        "source": "The National Archives, PRONOM",
        "derived_from": {
            "file": args.formats.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        "records": {
            "file": name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "count": len(records),
        },
        "licence": "OGL-UK-3.0",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} records to {OUT / name}")


if __name__ == "__main__":
    main()

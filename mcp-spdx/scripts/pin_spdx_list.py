# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Pin a release of the SPDX licence list as the data `dd_mcp_spdx` serves.

Downloads `json/licenses.json` at one tag of `spdx/license-list-data` and writes one JSON record
per licence, with a manifest, to `src/dd_mcp_spdx/data/`:

    uv run --no-project --python 3.14 mcp-spdx/scripts/pin_spdx_list.py v3.29.0

Run it after each SPDX licence-list release you adopt (about two a year), then commit the output
and update the copies the deployments pin (README.md, "Updating to a new release"). Each record
keeps the licence's identifier, name, SPDX page, the OSI and FSF flags, whether the identifier is
deprecated, and the URLs SPDX lists for its text; SPDX's internal `referenceNumber` and
`detailsUrl` are left out. The output is reproducible: the same release gives the same bytes.

The SPDX licence list data are under CC0-1.0 (`src/dd_mcp_spdx/data/LICENCE.md`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parents[1] / "src" / "dd_mcp_spdx" / "data"
SOURCE = "https://raw.githubusercontent.com/spdx/license-list-data/{tag}/json/licenses.json"
TAG = re.compile(r"^v(\d+\.\d+(?:\.\d+)?)$")


def record(entry: dict[str, Any]) -> dict[str, Any]:
    """One licence as it is stored: the fields the server answers, in a fixed order."""
    return {
        "licenseId": str(entry["licenseId"]),
        "name": str(entry["name"]),
        "reference": str(entry["reference"]),
        "isOsiApproved": bool(entry.get("isOsiApproved", False)),
        "isFsfLibre": entry.get("isFsfLibre"),
        "isDeprecatedLicenseId": bool(entry.get("isDeprecatedLicenseId", False)),
        "seeAlso": sorted(str(u) for u in entry.get("seeAlso", [])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("tag", help="a tag of spdx/license-list-data, such as v3.29.0")
    args = parser.parse_args()
    match = TAG.match(args.tag)
    if match is None:
        parser.error(f"not a release tag: {args.tag!r}")
    url = SOURCE.format(tag=args.tag)
    with urllib.request.urlopen(url, timeout=60) as resp:
        raw = resp.read()
    listed = json.loads(raw)
    version = str(listed["licenseListVersion"])
    if version != match.group(1):
        raise SystemExit(f"{url} is release {version}, not {match.group(1)}")
    records = sorted((record(e) for e in listed["licenses"]), key=lambda r: r["licenseId"])
    lines = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records)
    body = lines.encode("utf-8")
    name = f"licenses-{version}.jsonl"
    for old in OUT.glob("licenses-*.jsonl"):
        old.unlink()
    (OUT / name).write_bytes(body)
    manifest = {
        "licence_list_version": version,
        "release_date": str(listed["releaseDate"])[:10],
        "source": "SPDX licence list, spdx/license-list-data",
        "derived_from": {"url": url, "sha256": hashlib.sha256(raw).hexdigest()},
        "records": {
            "file": name,
            "sha256": hashlib.sha256(body).hexdigest(),
            "count": len(records),
        },
        "licence": "CC0-1.0",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{name}: {len(records)} licences, sha256 {manifest['records']['sha256']}")


if __name__ == "__main__":
    main()

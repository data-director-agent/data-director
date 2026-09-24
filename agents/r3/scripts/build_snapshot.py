"""Build data/fairsharing/snapshot.jsonl from data/fairsharing/ids.txt.

Each identifier is fetched through FAIRsharing's public record route (no account needed):
`GET https://fairsharing.org/<id>` with `Accept: application/json`. Records are projected to the
workbench's `Record` shape (see src/dd_agent_r3/fairsharing/records.py) and written one per line, with
a manifest recording when and how. A polite delay between requests keeps this well inside what a
public site should be asked to serve (P14).

FAIRsharing content is CC BY-SA 4.0; see data/fairsharing/LICENCE.md.

Usage: uv run python agents/r3/scripts/build_snapshot.py [--ids PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from dd_agent_r3.fairsharing.records import PUBLIC_RECORD_URL, Record, from_public_json

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "fairsharing"
IDS = DATA_DIR / "ids.txt"
SNAPSHOT = DATA_DIR / "snapshot.jsonl"
MANIFEST = DATA_DIR / "manifest.json"

DELAY_S = 0.5  # between requests; the public site is not an API
TIMEOUT_S = 30.0


def read_ids(path: Path) -> list[str]:
    ids: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        token = line.split("#", 1)[0].strip()
        if token:
            ids.append(token)
    return ids


def fetch(client: httpx.Client, fairsharing_id: str) -> Record | None:
    url = PUBLIC_RECORD_URL.format(id=fairsharing_id)
    resp = client.get(url, headers={"Accept": "application/json"})
    if resp.status_code != 200:
        print(f"  {fairsharing_id}: HTTP {resp.status_code}", file=sys.stderr)
        return None
    data = resp.json()
    if "name" not in data:
        print(f"  {fairsharing_id}: no record ({data.get('message', '?')})", file=sys.stderr)
        return None
    return from_public_json(data, source_uri=url)


def main(ids_path: str | None = None, out_path: str | None = None) -> int:
    ids_file = Path(ids_path) if ids_path else IDS
    out_file = Path(out_path) if out_path else SNAPSHOT
    ids = read_ids(ids_file)
    records: list[Record] = []
    missing: list[str] = []
    with httpx.Client(timeout=TIMEOUT_S, follow_redirects=True) as client:
        for i, fid in enumerate(ids, start=1):
            print(f"[{i}/{len(ids)}] {fid}", file=sys.stderr)
            rec = fetch(client, fid)
            if rec is None:
                missing.append(fid)
            else:
                records.append(rec)
            time.sleep(DELAY_S)

    # Dedupe on fairsharing_id (an id and its DOI suffix may both appear in ids.txt).
    unique = {r.fairsharing_id: r for r in records}
    ordered = sorted(unique.values(), key=lambda r: r.fairsharing_id)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as fh:
        for r in ordered:
            fh.write(r.model_dump_json(exclude_none=True) + "\n")
    digest = hashlib.sha256(out_file.read_bytes()).hexdigest()
    manifest = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": PUBLIC_RECORD_URL,
        "requested": len(ids),
        "records": len(ordered),
        "missing": missing,
        "sha256": digest,
        "licence": "CC BY-SA 4.0 — see LICENCE.md",
        "record_types": sorted({r.record_type or "?" for r in ordered}),
    }
    (out_file.parent / MANIFEST.name).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(ordered)} records to {out_file}; {len(missing)} missing", file=sys.stderr)
    return 0 if ordered else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ids", default=None)
    ap.add_argument("--out", default=None)
    ns = ap.parse_args()
    raise SystemExit(main(ns.ids, ns.out))

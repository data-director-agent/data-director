"""Rebuild the committed snapshots of re3data and FAIRsharing from their public routes.

    uv run python agents/repository/scripts/build_snapshot.py

Fetches every re3data identifier in `data/re3data/ids.txt`, then the FAIRsharing database record
each one cross-references. Writes `snapshot.jsonl` and `manifest.json` beside each. No account is
needed. A rebuilt snapshot has a new label and a new hash, so add entries for it to
`workbench/sources.yaml` and `app/config/sources.yaml`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from dd_agent_repository.live import FairsharingLive, Re3dataLive
from dd_agent_repository.records import FAIRSHARING_RECORD_URL, RE3DATA_RECORD_URL
from dd_agent_repository.snapshot import FAIRSHARING_SNAPSHOT, RE3DATA_SNAPSHOT

IDS = RE3DATA_SNAPSHOT.with_name("ids.txt")


def _write(path: Path, documents: list[dict[str, object]], manifest: dict[str, object]) -> None:
    lines = "".join(
        json.dumps(d, sort_keys=True, ensure_ascii=False) + "\n" for d in documents
    ).encode("utf-8")
    path.write_bytes(lines)
    manifest["sha256"] = hashlib.sha256(lines).hexdigest()
    path.with_name("manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> int:
    wanted = [
        line.split()[0]
        for line in IDS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    re3data, fairsharing = Re3dataLive(), FairsharingLive()

    repositories, missing = [], []
    for rid in wanted:
        record = re3data.fetch(rid)
        if record is None:
            missing.append(rid)
        else:
            repositories.append(record)
    _write(
        RE3DATA_SNAPSHOT,
        [r.document() for r in sorted(repositories, key=lambda r: r.re3data_id)],
        {
            "fetched_at": fetched_at,
            "source": RE3DATA_RECORD_URL,
            "requested": len(wanted),
            "records": len(repositories),
            "missing": missing,
            "licence": "CC0 1.0 (re3data metadata) — see LICENCE.md",
        },
    )

    cross = sorted({r.fairsharing_id for r in repositories if r.fairsharing_id})
    databases, fs_missing = [], []
    for fid in cross:
        db = fairsharing.fetch(fid)
        if db is None:
            fs_missing.append(fid)
        else:
            databases.append(db)
    _write(
        FAIRSHARING_SNAPSHOT,
        [d.document() for d in sorted(databases, key=lambda d: d.fairsharing_id)],
        {
            "fetched_at": fetched_at,
            "source": FAIRSHARING_RECORD_URL,
            "requested": len(cross),
            "records": len(databases),
            "missing": fs_missing,
            "licence": "CC BY-SA 4.0 — see LICENCE.md",
        },
    )
    print(
        f"re3data: {len(repositories)}/{len(wanted)} records; "
        f"FAIRsharing: {len(databases)}/{len(cross)} records",
        file=sys.stderr,
    )
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())

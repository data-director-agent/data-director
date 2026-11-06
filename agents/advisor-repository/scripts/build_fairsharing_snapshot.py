"""Rebuild the committed snapshot of FAIRsharing's database records from its public route.

    uv run python agents/advisor-repository/scripts/build_fairsharing_snapshot.py

Fetches again each FAIRsharing record the snapshot holds, and writes `snapshot.jsonl` and
`manifest.json` in `data/fairsharing/`. No account is needed. A rebuilt snapshot has a new label
and a new hash, so add entries for it to `workbench/sources.yaml` and `app/config/sources.yaml`.

re3data is not fetched here: it comes from its pinned monthly export (`dd-re3data fetch`). Which
FAIRsharing records to hold for the whole registry is TODO(#487).
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime

from dd_agent_advisor_repository.live import FairsharingLive
from dd_agent_advisor_repository.records import FAIRSHARING_RECORD_URL
from dd_agent_advisor_repository.snapshot import FAIRSHARING_SNAPSHOT, FairsharingSnapshot


def main() -> int:
    wanted = sorted(FairsharingSnapshot().records)
    live = FairsharingLive()
    databases, missing = [], []
    for fid in wanted:
        db = live.fetch(fid)
        if db is None:
            missing.append(fid)
        else:
            databases.append(db)
    lines = "".join(
        json.dumps(d.document(), sort_keys=True, ensure_ascii=False) + "\n"
        for d in sorted(databases, key=lambda d: d.fairsharing_id)
    ).encode("utf-8")
    FAIRSHARING_SNAPSHOT.write_bytes(lines)
    manifest = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": FAIRSHARING_RECORD_URL,
        "requested": len(wanted),
        "records": len(databases),
        "missing": missing,
        "licence": "CC BY-SA 4.0 — see LICENCE.md",
        "sha256": hashlib.sha256(lines).hexdigest(),
    }
    FAIRSHARING_SNAPSHOT.with_name("manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    sys.stderr.write(f"FAIRsharing: {len(databases)}/{len(wanted)} records\n")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())

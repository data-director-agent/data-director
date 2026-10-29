"""Rebuild the committed snapshot of FAIRsharing policy records.

    uv run python agents/policy/scripts/build_snapshot.py

Fetches every identifier in `data/fairsharing/ids.txt` with the live route's `fetch`, so the
snapshot holds the same documents a live run would hash. With `FAIRSHARING_LOGIN` and
`FAIRSHARING_PASSWORD` set, each record is read from the authenticated API and keeps its
relations; without them, from the public route, which has none. Writes `snapshot.jsonl` and
`manifest.json`. A rebuilt snapshot has a new label and a new hash, so add entries for it to
`workbench/sources.yaml` and `app/config/sources.yaml`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime

from dd_agent_policy.live import PolicyLive
from dd_agent_policy.records import PUBLIC_RECORD_URL
from dd_agent_policy.snapshot import SNAPSHOT

IDS = SNAPSHOT.with_name("ids.txt")


def main() -> int:
    wanted = [
        line.split()[0]
        for line in IDS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    live = PolicyLive()
    records, missing = [], []
    for fid in wanted:
        record = live.fetch(fid)
        if record is None:
            missing.append(fid)
        else:
            records.append(record)
    lines = "".join(
        json.dumps(r.document(), sort_keys=True, ensure_ascii=False) + "\n"
        for r in sorted(records, key=lambda r: r.fairsharing_id)
    ).encode("utf-8")
    SNAPSHOT.write_bytes(lines)
    manifest = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": PUBLIC_RECORD_URL,
        "authenticated": live.signed_in,
        "requested": len(wanted),
        "records": len(records),
        "missing": missing,
        "licence": "CC BY-SA 4.0 — see LICENCE.md",
        "sha256": hashlib.sha256(lines).hexdigest(),
    }
    SNAPSHOT.with_name("manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"FAIRsharing policy records: {len(records)}/{len(wanted)}", file=sys.stderr)
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())

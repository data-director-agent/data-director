"""Rebuild the committed snapshot of FAIRsharing's database records from its public route.

    uv run python agents/advisor-repository/scripts/build_fairsharing_snapshot.py \
        [--cited-by agents/advisor-repository/tests/data/re3data-export-fixture.zip]

Fetches again each FAIRsharing record the snapshot holds, and every one cited by the re3data
records in each `--cited-by` export, and writes `snapshot.jsonl` and `manifest.json` in
`data/fairsharing/`. Which records it holds is therefore a rule, not a list kept by hand: the
snapshot holds every FAIRsharing record the test fixture's repositories cite
(`test_the_fairsharing_snapshot_holds_every_record_the_fixture_cites`). Identifiers are compared
ignoring case, as FAIRsharing resolves them. No account is needed. A rebuilt snapshot has a new
label and a new hash, so add entries for it to `workbench/sources.yaml` and
`app/config/sources.yaml`.

re3data is not fetched here: it comes from its pinned monthly export (`dd-re3data fetch`). Which
FAIRsharing records to hold for the whole registry is TODO(#487).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from dd_agent_advisor_repository import registry
from dd_agent_advisor_repository.live import FairsharingLive
from dd_agent_advisor_repository.records import FAIRSHARING_RECORD_URL
from dd_agent_advisor_repository.snapshot import FAIRSHARING_SNAPSHOT, FairsharingSnapshot


def wanted(held: Iterable[str], cited: Iterable[str]) -> list[str]:
    """The identifiers to fetch: those held, and those cited that are not held in another
    case."""
    out = {fid.casefold(): fid for fid in cited}
    out.update({fid.casefold(): fid for fid in held})
    return sorted(out.values())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--cited-by",
        type=Path,
        action="append",
        default=[],
        help="a re3data export zip whose records' FAIRsharing citations to add",
    )
    args = parser.parse_args(argv)
    cited = [
        r.fairsharing_id
        for archive in args.cited_by
        for r in registry.records(archive)
        if r.fairsharing_id
    ]
    wanted_ids = wanted(FairsharingSnapshot().records, cited)
    live = FairsharingLive()
    databases, missing = [], []
    for fid in wanted_ids:
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
        "requested": len(wanted_ids),
        "records": len(databases),
        "missing": missing,
        "licence": "CC BY-SA 4.0 — see LICENCE.md",
        "sha256": hashlib.sha256(lines).hexdigest(),
    }
    FAIRSHARING_SNAPSHOT.with_name("manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    sys.stderr.write(f"FAIRsharing: {len(databases)}/{len(wanted_ids)} records\n")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())

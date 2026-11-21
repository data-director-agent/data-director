"""How long each test file takes, so that CI's pytest shards take about as long as each other.

CI runs the suite as three jobs side by side (`--test-shard`, the root conftest.py). A shard that
takes longer than the others sets how long every pull request waits, so the files are dealt out by
their recorded durations, longest first, each to the shard with the least so far. The durations
are in `scripts/test_durations.json`; a file not listed there, such as a new one, falls in a shard
by a stable hash of its path, so nothing has to be listed for the suite to run.

    uv run --no-project --python 3.14 scripts/test_durations.py .report-*.json

reads pytest-json-report files (CI's coverage job uploads the map it writes from them as the
`test-durations` artefact) and rewrites the map. The durations are the sum of each test's setup,
call and teardown; they need only be in proportion, so refresh the map when the shards drift
apart, not on every change.
"""

from __future__ import annotations

import argparse
import json
import sys
import zlib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DURATIONS = ROOT / "scripts" / "test_durations.json"


def load(path: Path = DURATIONS) -> dict[str, float]:
    """The recorded seconds per test file; empty when there is no map."""
    if not path.is_file():
        return {}
    data: dict[str, float] = json.loads(path.read_text(encoding="utf-8"))
    return data


def assign(durations: dict[str, float], count: int) -> dict[str, int]:
    """Each recorded file's shard, 1 to `count`: longest first, to the least-loaded shard.

    The result depends on the map alone, never on which tests a session collects, so every
    xdist worker and every shard agrees on it.
    """
    loads = [0.0] * count
    shards: dict[str, int] = {}
    for path, seconds in sorted(durations.items(), key=lambda item: (-item[1], item[0])):
        index = min(range(count), key=lambda i: (loads[i], i))
        loads[index] += seconds
        shards[path] = index + 1
    return shards


def shard_of(path: str, shards: dict[str, int], count: int) -> int:
    """The shard, 1 to `count`, that runs the test file at `path`."""
    if path in shards:
        return shards[path]
    return zlib.crc32(path.encode()) % count + 1


def from_reports(reports: list[Path]) -> dict[str, float]:
    """Seconds per test file, summed from pytest-json-report files."""
    seconds: Counter[str] = Counter()
    for report in reports:
        for test in json.loads(report.read_text(encoding="utf-8"))["tests"]:
            path = test["nodeid"].partition("::")[0]
            for phase in ("setup", "call", "teardown"):
                seconds[path] += test.get(phase, {}).get("duration", 0.0)
    return {path: round(total, 1) for path, total in sorted(seconds.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reports", nargs="+", type=Path, help="pytest-json-report files")
    parser.add_argument("--output", type=Path, default=DURATIONS, help="the map to write")
    args = parser.parse_args(argv)
    durations = from_reports(args.reports)
    if not durations:
        print("no tests in the reports", file=sys.stderr)
        return 1
    args.output.write_text(json.dumps(durations, indent=2) + "\n", encoding="utf-8")
    print(f"{args.output}: {len(durations)} files, {sum(durations.values()):.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

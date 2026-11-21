"""How scripts/test_durations.py deals test files to CI's pytest shards (`--test-shard`)."""

from __future__ import annotations

import json
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import test_durations as td  # noqa: E402

DURATIONS = {"a.py": 50.0, "b.py": 40.0, "c.py": 30.0, "d.py": 20.0, "e.py": 10.0, "f.py": 10.0}


def test_every_recorded_file_is_in_one_shard() -> None:
    shards = td.assign(DURATIONS, 3)
    assert set(shards) == set(DURATIONS)
    assert set(shards.values()) <= {1, 2, 3}


def test_shards_are_balanced() -> None:
    shards = td.assign(DURATIONS, 3)
    loads = [sum(s for p, s in DURATIONS.items() if shards[p] == i) for i in (1, 2, 3)]
    assert max(loads) - min(loads) <= max(DURATIONS.values())


def test_assignment_ignores_order() -> None:
    reordered = dict(reversed(list(DURATIONS.items())))
    assert td.assign(reordered, 3) == td.assign(DURATIONS, 3)


def test_unrecorded_file_falls_back_to_the_hash() -> None:
    shards = td.assign(DURATIONS, 3)
    path = "new/tests/test_new.py"
    assert td.shard_of(path, shards, 3) == zlib.crc32(path.encode()) % 3 + 1
    assert td.shard_of("a.py", shards, 3) == shards["a.py"]


@pytest.mark.parametrize("count", [1, 2, 3, 4])
def test_recorded_map_covers_every_shard(count: int) -> None:
    shards = td.assign(td.load(), count)
    assert set(shards.values()) == set(range(1, count + 1))


def test_map_from_reports(tmp_path: Path) -> None:
    report = tmp_path / ".report-1.json"
    tests = [
        {"nodeid": "x/test_a.py::t1", "setup": {"duration": 0.5}, "call": {"duration": 1.0}},
        {"nodeid": "x/test_a.py::t2", "call": {"duration": 2.0}, "teardown": {"duration": 0.5}},
        {"nodeid": "x/test_b.py::t", "setup": {"duration": 0.2}},
    ]
    report.write_text(json.dumps({"tests": tests}), encoding="utf-8")
    output = tmp_path / "durations.json"
    assert td.main([str(report), "--output", str(output)]) == 0
    assert td.load(output) == {"x/test_a.py": 4.0, "x/test_b.py": 0.2}

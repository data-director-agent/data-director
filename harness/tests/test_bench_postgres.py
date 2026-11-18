"""The PostgreSQL benchmark runs (harness/scripts/bench_postgres.py, docs/specs/evaluation.md,
Benchmark). What it measures is not checked: its figures are not conformance, so this test
carries no requirement marker. Skipped unless `DD_TEST_POSTGRES` names a database, as
`test_postgres.py` is."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DATABASE = os.environ.get("DD_TEST_POSTGRES", "")
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bench_postgres.py"

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not DATABASE, reason="no database: DD_TEST_POSTGRES is unset"),
]


def test_the_benchmark_runs_and_reports_each_measure(tmp_path: Path) -> None:
    pytest.importorskip("psycopg")
    out, tables = tmp_path / "bench.json", tmp_path / "bench.md"
    # Its own process: the writers are spawned processes that import the script as __main__.
    subprocess.run(
        [sys.executable, str(SCRIPT), "--quick", "--json", str(out), "--markdown", str(tables)],
        env={**os.environ, "DD_TEST_POSTGRES": DATABASE},
        check=True,
        capture_output=True,
        timeout=300,
    )
    results = json.loads(out.read_text(encoding="utf-8"))
    assert set(results) == {"identity", "invocation", "reads_by_store_size", "throughput"}
    assert results["identity"]["postgres_version"]
    assert set(results["invocation"]) == {"over_a2a", "direct"}
    assert [row["writers"] for row in results["throughput"]] == [1, 2]
    assert all(row["runs_per_s"] > 0 for row in results["throughput"])
    assert "not a budget" in tables.read_text(encoding="utf-8")

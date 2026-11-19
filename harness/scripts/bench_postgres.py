"""A first benchmark of the harness over the PostgreSQL run store: latency (Blueprint C10) and how
it holds up with more writers and a larger store (C11) (docs/specs/evaluation.md, Benchmark).

Every run goes through the conductor to a stub agent that abstains, so what is timed is the
harness's own work (policy gate, input check, linting, storing the envelope, trace and Process
Run Crate) and the database, not an agent or a model. It measures:

- one invocation's latency, with the agent reached over in-memory A2A and called directly;
- reading a page of runs, a page of conversations and one run, in a store of each `--sizes`;
- runs per second with 1, 2, 4 ... concurrent writers (`--writers`), each its own process with
  its own conductor and pool, as separate workers of one deployment would be.

The figures depend on the machine; they are a first number, not a budget, and nothing here
substantiates C10 or C11 (the Blueprint assesses both at deployment). Each run of the script
uses schemas of its own on `--database`, dropped afterwards.

    DD_TEST_POSTGRES=postgresql://postgres@localhost/postgres \\
        uv run python harness/scripts/bench_postgres.py --json bench.json --markdown bench.md

`--quick` takes a few samples of each, to check that the script runs.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import platform
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from dd_harness import postgres
from dd_harness.conductor import Conductor
from dd_harness.testing import (
    TEST_PRINCIPAL,
    AbstainingStub,
    make_conductor,
    message,
    request,
)
from dd_harness.testing.postgres import bulk_runs, scratch_schemas

HERE = Path(__file__).resolve().parent
# A page as the app asks for one.
PAGE = 20


def _ms(samples: list[float]) -> dict[str, float]:
    """p50, p95 and the slowest of `samples` seconds, in milliseconds."""
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    return {
        "n": len(ordered),
        "p50_ms": round(statistics.median(ordered) * 1000, 2),
        "p95_ms": round(p95 * 1000, 2),
        "max_ms": round(ordered[-1] * 1000, 2),
    }


def _timed(action: Callable[[], object], times: int) -> list[float]:
    samples = []
    for _ in range(times):
        began = time.perf_counter()
        action()
        samples.append(time.perf_counter() - began)
    return samples


def _invoke(conductor: Conductor) -> None:
    """One invocation, with an identifier of its own as every request must have."""
    conductor.invoke(request("stub.abstain", message()), acting_for=TEST_PRINCIPAL)


def invocation_latency(location: str, samples: int, *, remote: bool) -> dict[str, float]:
    """One invocation's latency, from the caller's side, crate included."""
    conductor = make_conductor(location, AbstainingStub(), crate=True, remote=remote)
    try:
        _invoke(conductor)  # warm up
        return _ms(_timed(lambda: _invoke(conductor), samples))
    finally:
        conductor.close()


def read_latency(location: str, samples: int) -> dict[str, dict[str, float]]:
    """Reading a page of runs, a page of conversations and one run from the store."""
    with postgres.PostgresRunStore(location) as store:
        first = store.list_runs(limit=1).items[0]["invocation_id"]
        reads: dict[str, Callable[[], object]] = {
            "list_runs": lambda: store.list_runs(limit=PAGE),
            "list_conversations": lambda: store.list_conversations(limit=PAGE),
            "get": lambda: store.get(first),
        }
        for read in reads.values():
            read()  # warm up
        return {name: _ms(_timed(read, samples)) for name, read in reads.items()}


def _writer(location: str, runs: int, start: Any, out: Any) -> None:
    """One worker: its own conductor, `runs` invocations once every worker is ready."""
    conductor = make_conductor(location, AbstainingStub(), crate=True, remote=False)
    _invoke(conductor)  # warm up
    start.wait()
    began = time.perf_counter()
    for _ in range(runs):
        _invoke(conductor)
    out.put(time.perf_counter() - began)
    conductor.close()


def throughput(location: str, writers: int, runs_each: int) -> dict[str, float]:
    """Runs stored per second by `writers` processes writing at once."""
    spawn = multiprocessing.get_context("spawn")
    start, out = spawn.Barrier(writers + 1), spawn.Queue()
    workers = [
        spawn.Process(target=_writer, args=(location, runs_each, start, out))
        for _ in range(writers)
    ]
    for worker in workers:
        worker.start()
    start.wait()
    began = time.perf_counter()
    elapsed = [out.get(timeout=600) for _ in workers]
    wall = time.perf_counter() - began
    for worker in workers:
        worker.join()
        if worker.exitcode:
            raise RuntimeError(f"a writer exited with {worker.exitcode}")
    total = writers * runs_each
    return {
        "writers": writers,
        "runs": total,
        "runs_per_s": round(total / wall, 1),
        "per_run_ms": round(statistics.mean(elapsed) / runs_each * 1000, 2),
    }


def identity(database: str) -> dict[str, Any]:
    """What the figures depend on, so two runs can be compared."""
    with psycopg.connect(database) as conn:
        row = conn.execute("show server_version").fetchone()
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, check=False
    ).stdout.strip()
    return {
        "git_revision": revision or None,
        "postgres_version": row[0] if row else None,
        "python": platform.python_version(),
        "machine": platform.machine(),
        "cpus": os.cpu_count(),
        "runner": os.environ.get("RUNNER_NAME") or platform.node(),
        "pool_size": postgres.DEFAULT_POOL_SIZE,
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def run(
    database: str, *, samples: int, sizes: list[int], writers: list[int], runs_each: int
) -> dict[str, Any]:
    results: dict[str, Any] = {"identity": identity(database)}
    with scratch_schemas(database) as schemas:
        results["invocation"] = {
            "over_a2a": invocation_latency(schemas.migrated("a2a"), samples, remote=True),
            "direct": invocation_latency(schemas.migrated("direct"), samples, remote=False),
        }
        reads = {}
        for size in sizes:
            location = schemas.blank(f"size_{size}")
            bulk_runs(location, size)
            reads[str(size)] = read_latency(location, samples)
        results["reads_by_store_size"] = reads
        results["throughput"] = [
            throughput(schemas.migrated(f"writers_{n}"), n, runs_each) for n in writers
        ]
    return results


def markdown(results: dict[str, Any]) -> str:
    """The results as tables, for a job summary."""
    who = results["identity"]
    lines = [
        "## PostgreSQL benchmark (C10, C11)",
        "",
        f"PostgreSQL {who['postgres_version']}, Python {who['python']}, {who['cpus']} CPUs, "
        f"pool {who['pool_size']}, revision `{(who['git_revision'] or '?')[:12]}`. A first "
        "number for this machine, not a budget; it substantiates neither requirement.",
        "",
        "| Invocation (stub agent, crate written) | n | p50 ms | p95 ms | max ms |",
        "|---|---|---|---|---|",
    ]
    for name, figures in results["invocation"].items():
        lines.append(f"| {name.replace('_', ' ')} | " + _cells(figures))
    lines += [
        "",
        "| Read | Runs in store | n | p50 ms | p95 ms | max ms |",
        "|---|---|---|---|---|---|",
    ]
    for size, reads in results["reads_by_store_size"].items():
        for name, figures in reads.items():
            lines.append(f"| `{name}` | {int(size):,} | " + _cells(figures))
    lines += ["", "| Concurrent writers | Runs | Runs/s | Mean ms per run |", "|---|---|---|---|"]
    for row in results["throughput"]:
        lines.append(
            f"| {row['writers']} | {row['runs']} | {row['runs_per_s']} | {row['per_run_ms']} |"
        )
    return "\n".join(lines) + "\n"


def _cells(figures: dict[str, float]) -> str:
    return f"{figures['n']} | {figures['p50_ms']} | {figures['p95_ms']} | {figures['max_ms']} |"


def _numbers(text: str) -> list[int]:
    return [int(n) for n in text.split(",") if n]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--database", default=os.environ.get("DD_TEST_POSTGRES", ""))
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--sizes", type=_numbers, default=[1000, 20000])
    parser.add_argument("--writers", type=_numbers, default=[1, 2, 4, 8])
    parser.add_argument("--runs-each", type=int, default=100)
    parser.add_argument("--quick", action="store_true", help="a few samples of each")
    parser.add_argument("--json", type=Path, help="write the results here as JSON")
    parser.add_argument("--markdown", type=Path, help="write the tables here")
    args = parser.parse_args(argv)
    if not args.database:
        parser.error("name a database with --database or DD_TEST_POSTGRES")
    if args.quick:
        args.samples, args.sizes, args.writers, args.runs_each = 5, [200], [1, 2], 5
    results = run(
        args.database,
        samples=args.samples,
        sizes=args.sizes,
        writers=args.writers,
        runs_each=args.runs_each,
    )
    tables = markdown(results)
    if args.json:
        args.json.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", "utf-8")
    if args.markdown:
        args.markdown.write_text(tables, encoding="utf-8")
    sys.stdout.write(tables)
    return 0


if __name__ == "__main__":
    sys.exit(main())

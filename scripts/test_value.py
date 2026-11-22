"""Which tests add something the others do not: a report to read, not a check that fails.

The suite has thousands of cases, and a count alone does not say whether that is too many. This
runs the suite once with coverage recorded per test (coverage.py's dynamic contexts) and prints
three lists in Markdown:

- **Nothing new**: per test file, the test functions that reach no line that some other test
  function does not also reach. Such a test is a candidate to merge or remove, not proof that it
  is redundant: two tests can take the same lines with different inputs and check different
  results. Which of them catches a fault is what mutation testing measures; the weekly run is
  `.github/workflows/mutation.yml`, over the governance modules.
- **Fan-out**: parametrised test functions whose cases take far fewer distinct paths through
  the code than there are cases. A function with 165 cases and 3 paths is usually one check
  run once per file, which could be one test that reports every file, or a `check_*.py` script.
- **Reaches no code**: test functions that passed but ran no measured line during the test
  itself. They test configuration, data or files, or exercise only code imported before the
  test started.

    uv run python scripts/test_value.py                    # the whole suite, about 3 minutes
    uv run python scripts/test_value.py -- harness/tests   # pytest arguments after --
    uv run python scripts/test_value.py --reuse            # report the last run again

The run's data is kept in `.test-value/`. The report always exits 0; nothing in CI runs it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from coverage import CoverageData

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".test-value"

# A parametrised function with at least this many cases is checked for fan-out.
FAN_OUT_MIN_CASES = 10
# How many fan-out entries to print, most cases per distinct path first.
FAN_OUT_SHOWN = 25

Line = tuple[str, int]
PHASE = re.compile(r"\|(setup|run|teardown)$")
PARAMETERS = re.compile(r"\[.*\]$", re.DOTALL)


def case_of(context: str) -> str | None:
    """The pytest node ID a coverage context belongs to, or None for code run outside a test."""
    case = PHASE.sub("", context)
    return case or None


def function_of(case: str) -> str:
    """A node ID without its parameters: every case of a parametrised test shares it."""
    return PARAMETERS.sub("", case)


@dataclass
class FanOut:
    function: str
    cases: int
    paths: int


@dataclass
class Report:
    functions: int
    cases: int
    # test file -> (functions that reach nothing new, functions in the file that reach any code)
    nothing_new: dict[str, tuple[list[str], int]] = field(default_factory=dict)
    fan_out: list[FanOut] = field(default_factory=list)
    reaches_no_code: list[str] = field(default_factory=list)


def analyse(reach: Mapping[str, frozenset[Line]], passed: Iterable[str]) -> Report:
    """The report, from the lines each case reached and the cases that passed."""
    by_function: dict[str, set[Line]] = defaultdict(set)
    cases: dict[str, dict[str, frozenset[Line]]] = defaultdict(dict)
    for case, lines in reach.items():
        name = function_of(case)
        by_function[name] |= lines
        cases[name][case] = lines

    reached_by = Counter(line for lines in by_function.values() for line in lines)
    per_file: dict[str, tuple[list[str], int]] = {}
    for name in sorted(by_function):
        path = name.split("::", 1)[0]
        stale, total = per_file.get(path, ([], 0))
        if all(reached_by[line] > 1 for line in by_function[name]):
            stale.append(name.split("::", 1)[1])
        per_file[path] = (stale, total + 1)

    fan_out = [
        FanOut(name, len(each), len(set(each.values())))
        for name, each in cases.items()
        if len(each) >= FAN_OUT_MIN_CASES and len(set(each.values())) < len(each)
    ]
    fan_out.sort(key=lambda f: (-f.cases / f.paths, f.function))

    passed_functions = {function_of(case) for case in passed}
    return Report(
        functions=len(passed_functions | set(by_function)),
        cases=len(set(passed) | set(reach)),
        nothing_new={path: entry for path, entry in per_file.items() if entry[0]},
        fan_out=fan_out,
        reaches_no_code=sorted(passed_functions - set(by_function)),
    )


def render(report: Report) -> str:
    """The report as Markdown."""
    stale = sum(len(names) for names, _ in report.nothing_new.values())
    out = [
        "# Test value",
        "",
        f"{report.cases} cases in {report.functions} test functions.",
        "",
        "## Nothing new",
        "",
        f"{stale} test functions reach no line that another test function does not also reach.",
        "Same lines are not the same check: confirm with mutation testing before removing one.",
        "",
        "| Test file | Nothing new | Of |",
        "|---|---:|---:|",
    ]
    ranked = sorted(report.nothing_new.items(), key=lambda item: (-len(item[1][0]), item[0]))
    out += [f"| `{path}` | {len(names)} | {total} |" for path, (names, total) in ranked]
    out += [
        "",
        "## Fan-out",
        "",
        f"Parametrised functions with at least {FAN_OUT_MIN_CASES} cases and fewer distinct "
        "paths than cases, most cases per path first.",
        "",
        "| Test function | Cases | Distinct paths |",
        "|---|---:|---:|",
    ]
    out += [f"| `{f.function}` | {f.cases} | {f.paths} |" for f in report.fan_out[:FAN_OUT_SHOWN]]
    out += [
        "",
        "## Reaches no code",
        "",
        f"{len(report.reaches_no_code)} test functions passed without running a measured line.",
        "",
    ]
    out += [f"- `{name}`" for name in report.reaches_no_code]
    return "\n".join(out) + "\n"


def read_reach(coverage_file: Path) -> dict[str, frozenset[Line]]:
    """The lines each test case reached, from coverage data recorded with `--cov-context=test`."""
    data = CoverageData(basename=str(coverage_file))
    data.read()
    reach: dict[str, set[Line]] = defaultdict(set)
    for path in data.measured_files():
        relative = os.path.relpath(path, ROOT)
        for number, contexts in data.contexts_by_lineno(path).items():
            for context in contexts:
                if case := case_of(context):
                    reach[case].add((relative, number))
    return {case: frozenset(lines) for case, lines in reach.items()}


def read_passed(json_report: Path) -> list[str]:
    """The node IDs of the cases that passed, from a pytest-json-report file."""
    tests = json.loads(json_report.read_text(encoding="utf-8")).get("tests", [])
    return [test["nodeid"] for test in tests if test.get("outcome") == "passed"]


def run_suite(data: Path, pytest_args: list[str]) -> int:
    """Run pytest with per-test coverage contexts, writing the data into `data`."""
    data.mkdir(exist_ok=True)
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    sources = [*pyproject["tool"]["coverage"]["run"]["source_pkgs"], "scripts"]
    # sys.monitoring, coverage.py's default core on Python 3.12+, records no dynamic contexts.
    env = {**os.environ, "COVERAGE_CORE": "ctrace", "COVERAGE_FILE": str(data / ".coverage")}
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *(f"--cov={source}" for source in sources),
        "--cov-context=test",
        "--cov-report=",
        "--cov-fail-under=0",
        "--json-report",
        f"--json-report-file={data / 'report.json'}",
        "--json-report-omit",
        "collectors",
        "log",
        "traceback",
        "streams",
        "warnings",
        "keywords",
        *pytest_args,
    ]
    # pytest's own output goes to stderr, so that stdout holds the report alone.
    return subprocess.run(command, cwd=ROOT, env=env, stdout=sys.stderr, check=False).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reuse", action="store_true", help="report the last run's data again")
    parser.add_argument("--data", type=Path, default=DATA, help="where the run's data is kept")
    parser.add_argument("pytest_args", nargs="*", help="arguments for pytest, after --")
    args = parser.parse_args(argv)

    if not args.reuse:
        status = run_suite(args.data, args.pytest_args)
        if status not in (0, 1):
            print(f"pytest stopped with status {status}; no report.", file=sys.stderr)
            return 0
    coverage_file, json_report = args.data / ".coverage", args.data / "report.json"
    if not (coverage_file.is_file() and json_report.is_file()):
        print(f"No data in {args.data}: run without --reuse first.", file=sys.stderr)
        return 0
    print(render(analyse(read_reach(coverage_file), read_passed(json_report))), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())

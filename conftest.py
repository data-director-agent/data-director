"""Shared fixtures for the whole workspace's test session.

Two things happen here that the conformance report depends on:

- the `requirement` marker is checked against docs/requirements.yaml at collection
  time, so a test cannot claim to substantiate an identifier nobody has registered, or one the
  register assesses by human review only (docs/specs/evaluation.md);
- `pytest_json_runtest_metadata` copies the marker's identifiers into the pytest-json-report
  record, which is what scripts/conformance_report.py reads.

With `--test-shard 2/3` the session runs one part of the suite (`_keep_shard`), the files dealt
to it by their recorded durations (scripts/test_durations.py). It is an option, not an environment
variable, so a test that starts pytest itself does not pass it on.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import settings

ROOT = Path(__file__).resolve().parent
REGISTER = ROOT / "docs" / "requirements.yaml"

# Property tests (Hypothesis) run a bounded number of examples, so they keep to the suite's time
# budget, and have no per-example deadline, which a loaded CI runner would miss at random. A test
# that needs fewer examples, such as one against a database, says so with its own `@settings`.
settings.register_profile("data-director", max_examples=50, deadline=None, print_blob=True)
settings.load_profile("data-director")


def _registered_requirements() -> dict[str, list[str]]:
    """requirement id -> the lanes it is assessed in; `test` alone when the register names none."""
    register = yaml.safe_load(REGISTER.read_text(encoding="utf-8"))
    return {e["id"]: e.get("assessed_by", ["test"]) for e in register["requirements"]}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--test-shard",
        default="",
        metavar="INDEX/COUNT",
        help="run one part of the suite, such as 2/3, as CI's parallel pytest jobs do",
    )


def _shard(config: pytest.Config) -> tuple[int, int] | None:
    """(index, count) from --test-shard, such as `2/3`; None runs the whole suite."""
    value: str = config.getoption("--test-shard")
    if not value:
        return None
    index, _, count = value.partition("/")
    if not (index.isdigit() and count.isdigit() and 1 <= int(index) <= int(count)):
        raise pytest.UsageError(f"--test-shard {value!r}: expected `index/count`, such as 2/3")
    return int(index), int(count)


def _shard_rules() -> Any:
    """scripts/test_durations.py, loaded by path: scripts/ is tooling, not an importable package."""
    spec = importlib.util.spec_from_file_location(
        "_test_durations", ROOT / "scripts" / "test_durations.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _keep_shard(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Keep the test files that fall in this shard, so CI can run the suite as parallel jobs.

    Files with a recorded duration are dealt out so that the shards take about as long as each
    other; any other file falls in a shard by a stable hash of its path, so a new file joins one
    without a list to update. Every file is in exactly one shard, and each xdist worker selects
    the same tests.
    """
    shard = _shard(config)
    if shard is None:
        return
    index, count = shard
    rules = _shard_rules()
    shards = rules.assign(rules.load(), count)
    keep: list[pytest.Item] = []
    drop: list[pytest.Item] = []
    for item in items:
        path = item.nodeid.partition("::")[0]
        (keep if rules.shard_of(path, shards, count) == index else drop).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    _keep_shard(config, items)
    known = _registered_requirements()
    for item in items:
        for marker in item.iter_markers("requirement"):
            unknown = [rid for rid in marker.args if rid not in known]
            if unknown:
                raise pytest.UsageError(
                    f"{item.nodeid}: requirement marker names unregistered identifiers {unknown}; "
                    "add them to docs/requirements.yaml first"
                )
            untestable = [rid for rid in marker.args if "test" not in known[rid]]
            if untestable:
                raise pytest.UsageError(
                    f"{item.nodeid}: requirement marker names {untestable}, which the register "
                    "assesses by review only; see docs/specs/evaluation.md"
                )


@pytest.hookimpl(optionalhook=True)
def pytest_json_runtest_metadata(item: pytest.Item, call: pytest.CallInfo[Any]) -> dict[str, Any]:
    if call.when != "call":
        return {}
    ids = [rid for marker in item.iter_markers("requirement") for rid in marker.args]
    return {"requirements": ids} if ids else {}


# How to run the PostgreSQL storage tests (harness/tests/test_postgres.py) locally, as CI does.
POSTGRES_HINT = (
    "docker run -d --rm -p 5432:5432 -e POSTGRES_PASSWORD=dd-test postgres:17, then "
    "DD_TEST_POSTGRES=postgresql://postgres@localhost:5432/postgres PGPASSWORD=dd-test "
    "uv run pytest -m postgres"
)


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """Say so when the PostgreSQL storage tests were skipped, so that a local run that passes is
    not mistaken for one that tested both storage backends."""
    skipped = [r for r in terminalreporter.stats.get("skipped", []) if "postgres" in r.keywords]
    if skipped:
        terminalreporter.write_sep("-", "PostgreSQL storage tests skipped", yellow=True)
        terminalreporter.write_line(
            f"{len(skipped)} PostgreSQL backend tests did not run: DD_TEST_POSTGRES is unset."
        )
        terminalreporter.write_line(f"To run them: {POSTGRES_HINT}")


@pytest.fixture(scope="session")
def vcr_config() -> dict[str, Any]:
    # record_mode is deliberately absent: setting it here would override --record-mode on the
    # command line, and CI relies on the command line saying `none`.
    return {
        "filter_headers": ["authorization", "x-api-key", "cookie", "set-cookie"],
        "filter_post_data_parameters": ["password"],
        "decode_compressed_response": True,
    }


@pytest.fixture
def runs_dir(tmp_path: Path) -> Path:
    return tmp_path / "runs"

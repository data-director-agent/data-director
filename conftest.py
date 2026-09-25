"""Shared fixtures for the whole workspace's test session.

Two things happen here that the conformance report depends on:

- the `requirement` marker is checked against workbench/docs/requirements.yaml at collection
  time, so a test cannot claim to substantiate an identifier nobody has registered, or one the
  register assesses by human review only (ADR-0014);
- `pytest_json_runtest_metadata` copies the marker's identifiers into the pytest-json-report
  record, which is what workbench/scripts/conformance_report.py reads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent
REGISTER = ROOT / "workbench" / "docs" / "requirements.yaml"


def _registered_requirements() -> dict[str, list[str]]:
    """requirement id -> the lanes it is assessed in; `test` alone when the register names none."""
    register = yaml.safe_load(REGISTER.read_text(encoding="utf-8"))
    return {e["id"]: e.get("assessed_by", ["test"]) for e in register["requirements"]}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    known = _registered_requirements()
    for item in items:
        for marker in item.iter_markers("requirement"):
            unknown = [rid for rid in marker.args if rid not in known]
            if unknown:
                raise pytest.UsageError(
                    f"{item.nodeid}: requirement marker names unregistered identifiers {unknown}; "
                    "add them to workbench/docs/requirements.yaml first"
                )
            untestable = [rid for rid in marker.args if "test" not in known[rid]]
            if untestable:
                raise pytest.UsageError(
                    f"{item.nodeid}: requirement marker names {untestable}, which the register "
                    "assesses by review only; see workbench/docs/adr/0014-assessment-lanes.md"
                )


@pytest.hookimpl(optionalhook=True)
def pytest_json_runtest_metadata(item: pytest.Item, call: pytest.CallInfo[Any]) -> dict[str, Any]:
    if call.when != "call":
        return {}
    ids = [rid for marker in item.iter_markers("requirement") for rid in marker.args]
    return {"requirements": ids} if ids else {}


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

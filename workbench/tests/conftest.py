"""Shared fixtures.

Two things happen here that the conformance report depends on:

- the `requirement` marker is checked against docs/requirements.yaml at collection time, so a
  test cannot claim to substantiate an identifier nobody has registered;
- `pytest_json_runtest_metadata` copies the marker's identifiers into the pytest-json-report
  record, which is what scripts/conformance_report.py reads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _registered_requirement_ids() -> set[str]:
    register = yaml.safe_load((ROOT / "docs" / "requirements.yaml").read_text(encoding="utf-8"))
    return {entry["id"] for entry in register["requirements"]}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    known = _registered_requirement_ids()
    for item in items:
        for marker in item.iter_markers("requirement"):
            unknown = [rid for rid in marker.args if rid not in known]
            if unknown:
                raise pytest.UsageError(
                    f"{item.nodeid}: requirement marker names unregistered identifiers {unknown}; "
                    "add them to docs/requirements.yaml first"
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

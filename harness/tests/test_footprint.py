"""Estimated energy and cost of a run's model calls (P14, C17; docs/specs/disclosure.md,
Footprint)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from dd_harness.footprint import Estimate, FootprintTable, estimate_call, total
from dd_harness.policy import PolicyError, load_profile
from dd_harness.testing import (
    PERMISSIVE,
    TEST_PRINCIPAL,
    DocumentStub,
    document_request,
    make_conductor,
    request,
)
from dd_sdk.contract.models import EnergyMethod, Envelope, OutcomeStatus

MODEL = "test-model-2026-11-01"
# The document double reports 12 input and 34 output tokens for its one call.
ENERGY_J = 12 * 0.5 + 34 * 2.0
COST = (12 * 3.0 + 34 * 15.0) / 1_000_000
FOOTPRINT = f"""
model_footprint:
  source: Test figures, not a published source
  as_of: 2026-11-01
  currency: GBP
  models:
    {MODEL}:
      input_per_mtok: 3.0
      output_per_mtok: 15.0
      input_j_per_token: 0.5
      output_j_per_token: 2.0
"""


def _profile(tmp_path: Path, footprint: str = FOOTPRINT) -> Path:
    path = tmp_path / "footprint.yaml"
    path.write_text(PERMISSIVE.read_text(encoding="utf-8") + footprint, encoding="utf-8")
    return path


def _drafted(runs_dir: Path, profile: Path, model: str = MODEL) -> Envelope:
    conductor = make_conductor(runs_dir, DocumentStub(model), crate=True, profile=profile)
    envelope = conductor.invoke(
        request("stub.document", document_request()), acting_for=TEST_PRINCIPAL
    )
    assert envelope.outcome.status == OutcomeStatus.SUCCEEDED, envelope.outcome.statement
    return envelope


def _crate(runs_dir: Path, envelope: Envelope) -> dict[str, dict[str, Any]]:
    path = runs_dir / envelope.invocation_id / "crate" / "ro-crate-metadata.json"
    return {e["@id"]: e for e in json.loads(path.read_text(encoding="utf-8"))["@graph"]}


def _figures(graph: dict[str, dict[str, Any]], action_id: str) -> dict[str, dict[str, Any]]:
    """The `PropertyValue`s an action names, by name."""
    named = graph[action_id].get("additionalProperty", [])
    named = named if isinstance(named, list) else [named]
    return {graph[n["@id"]]["name"]: graph[n["@id"]] for n in named}


@pytest.mark.requirement("P14.1", "C17.1")
def test_a_runs_crate_records_estimated_energy_and_cost_per_call_and_per_run(
    runs_dir: Path, tmp_path: Path
) -> None:
    envelope = _drafted(runs_dir, _profile(tmp_path))
    assert envelope.telemetry.energy_method is EnergyMethod.ESTIMATED
    assert envelope.telemetry.energy_estimate_j == pytest.approx(ENERGY_J)

    graph = _crate(runs_dir, envelope)
    call = _figures(graph, f"#{envelope.invocation_id}-model-call-1")
    assert (call["input_tokens"]["value"], call["output_tokens"]["value"]) == (12, 34)
    assert call["energy_estimate_j"]["value"] == pytest.approx(ENERGY_J)
    assert call["energy_estimate_j"]["unitCode"] == "JOU"
    assert call["cost_estimate"]["value"] == pytest.approx(COST)
    assert call["cost_estimate"]["unitText"] == "GBP"
    # A reader is told the figures are modelled, and from what.
    assert "not measured" in call["energy_estimate_j"]["description"]
    assert (
        "Test figures, not a published source (as of 2026-11-01)"
        in (call["cost_estimate"]["description"])
    )

    run = _figures(graph, f"#{envelope.invocation_id}")
    assert run["energy_estimate_j"]["value"] == pytest.approx(ENERGY_J)
    assert run["cost_estimate"]["value"] == pytest.approx(COST)


@pytest.mark.requirement("P14.1", "C17.1")
def test_a_model_the_table_does_not_list_is_not_estimated_never_zero(
    runs_dir: Path, tmp_path: Path
) -> None:
    envelope = _drafted(runs_dir, _profile(tmp_path), model="unlisted-model")
    assert envelope.telemetry.energy_method is EnergyMethod.NOT_MEASURED
    assert envelope.telemetry.energy_estimate_j is None

    graph = _crate(runs_dir, envelope)
    call = _figures(graph, f"#{envelope.invocation_id}-model-call-1")
    assert set(call) == {"model_account", "input_tokens", "output_tokens"}
    assert _figures(graph, f"#{envelope.invocation_id}") == {}


def test_a_profile_without_a_table_estimates_nothing(runs_dir: Path) -> None:
    envelope = _drafted(runs_dir, PERMISSIVE)
    assert envelope.telemetry.energy_method is EnergyMethod.NOT_MEASURED
    graph = _crate(runs_dir, envelope)
    assert "energy_estimate_j" not in _figures(graph, f"#{envelope.invocation_id}-model-call-1")


def test_a_run_is_estimated_only_if_every_call_is() -> None:
    assert total([Estimate(1.0, 0.5), Estimate(2.0, None)]) == Estimate(3.0, None)
    assert total([]) == Estimate()  # no model call: nothing was modelled


def test_a_call_without_token_counts_is_not_estimated() -> None:
    table = FootprintTable.from_value(
        {
            "source": "s",
            "as_of": date(2026, 11, 1),
            "models": {"m": {"input_j_per_token": 1, "output_j_per_token": 1}},
        }
    )
    assert estimate_call(table, "m", None, 3) == Estimate()
    assert estimate_call(table, "m", 2, 3) == Estimate(5.0, None)  # energy only, no prices


@pytest.mark.parametrize(
    ("written", "says"),
    [
        ("model_footprint:\n  as_of: 2026-11-01\n", "source"),
        ("model_footprint:\n  source: s\n  as_of: soon\n", "as_of"),
        (
            "model_footprint:\n  source: s\n  as_of: 2026-11-01\n  models:\n"
            "    m: {input_per_mtok: 1, output_per_mtok: 1}\n",
            "currency",
        ),
        (
            "model_footprint:\n  source: s\n  as_of: 2026-11-01\n  models:\n"
            "    m: {input_j_per_token: -1}\n",
            "at least 0",
        ),
        (
            "model_footprint:\n  source: s\n  as_of: 2026-11-01\n  models:\n    m: {joules: 1}\n",
            "nothing reads",
        ),
    ],
)
def test_a_malformed_table_refuses_the_profile(tmp_path: Path, written: str, says: str) -> None:
    with pytest.raises(PolicyError, match=says):
        load_profile(_profile(tmp_path, "\n" + written))

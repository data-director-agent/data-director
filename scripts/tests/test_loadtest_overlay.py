"""Every model-backed agent in the load-test stack uses the fake model (loadtest/README.md).

A model-backed agent the overlay misses would call the real provider whenever a key sits in
config/local/, costing money and distorting the figures. The overlay is read beside compose.yaml,
so a new advisor or orchestrator that the overlay lacks fails here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def services(path: str) -> dict[str, Any]:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))["services"]


BASE = services("compose.yaml")
OVERLAY = services("loadtest/compose.loadtest.yaml")
# The model-backed agents: the orchestrator and every adviser. The stub and the example call no model.
MODEL_BACKED = sorted(name for name in BASE if name == "orchestrator-model" or name.startswith("advisor-"))


def test_the_roster_of_model_backed_agents_is_found() -> None:
    assert "orchestrator-model" in MODEL_BACKED
    assert {"advisor-files", "advisor-linking", "advisor-quality"} <= set(MODEL_BACKED)


@pytest.mark.parametrize("name", MODEL_BACKED)
def test_the_overlay_points_the_agent_at_the_fake_model(name: str) -> None:
    assert name in OVERLAY, f"{name} is not in loadtest/compose.loadtest.yaml"
    env = OVERLAY[name]["environment"]
    assert env["ANTHROPIC_BASE_URL"] == "http://fake-llm:8080"
    assert env["DD_MODEL_BROKER_URL"] == ""
    # Blank, so a real key file in config/local/ is not used.
    assert env["ANTHROPIC_API_KEY_FILE"] == ""
    assert "fake-llm" in OVERLAY[name]["depends_on"]

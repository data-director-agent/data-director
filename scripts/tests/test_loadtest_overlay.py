"""loadtest/compose.loadtest.yaml points every model-backed agent at the fake model, so a load test
with a real key in config/local/ makes no provider calls (loadtest/README.md, #1259).

The model-backed agents are those `dd.py setup` can give a key: `MODEL_BACKED` and
`MODEL_BY_DEFAULT` (scripts/ddtool/common.py). Each one's environment is merged as Compose merges
an overlay: the overlay's keys replace the base file's, and `environment` wins over `env_file`,
so the key `dd.py setup` names in config/local/agents/<agent>.env is overridden.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ddtool.common import MODEL_BACKED, MODEL_BY_DEFAULT  # noqa: E402

BASE = ROOT / "compose.yaml"
OVERLAY = ROOT / "loadtest" / "compose.loadtest.yaml"
FAKE = "fake-llm"
# What each model-backed agent's merged environment must hold: the Anthropic client sends its
# calls to the fake model, with a placeholder key, and no key file or broker in its place.
FAKE_ENV = {
    "DD_MODEL_PROVIDER": "anthropic",
    "DD_MODEL_BROKER_URL": "",
    "ANTHROPIC_BASE_URL": f"http://{FAKE}:8080",
    "ANTHROPIC_API_KEY": "load-test-not-a-key",
    "ANTHROPIC_API_KEY_FILE": "",
}
MODEL_AGENTS = sorted(MODEL_BACKED | MODEL_BY_DEFAULT.keys())


def services(path: Path) -> dict[str, dict[str, Any]]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["services"]


def environment(service: dict[str, Any]) -> dict[str, str]:
    """A service's `environment`, in either of Compose's forms, as a mapping."""
    env = service.get("environment") or {}
    if isinstance(env, list):
        env = dict(item.partition("=")[::2] for item in env)
    return {name: "" if value is None else str(value) for name, value in env.items()}


def merged_environment(agent: str) -> dict[str, str]:
    return environment(services(BASE)[agent]) | environment(services(OVERLAY).get(agent, {}))


def test_every_model_agent_is_a_service() -> None:
    """The list checked below names the stack's services, so the check is not vacuous."""
    assert set(MODEL_AGENTS) <= services(BASE).keys()


def test_the_overlay_names_only_services_the_stack_has() -> None:
    assert services(OVERLAY).keys() - {FAKE} <= services(BASE).keys()


@pytest.mark.parametrize("agent", MODEL_AGENTS)
def test_the_agent_uses_the_fake_model(agent: str) -> None:
    env = merged_environment(agent)
    assert {name: env.get(name) for name in FAKE_ENV} == FAKE_ENV


@pytest.mark.parametrize("agent", MODEL_AGENTS)
def test_the_agent_waits_for_the_fake_model(agent: str) -> None:
    depends_on = services(OVERLAY)[agent].get("depends_on") or {}
    assert depends_on.get(FAKE) == {"condition": "service_healthy"}

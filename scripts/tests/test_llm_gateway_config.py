"""The LiteLLM gateway's limits on runaway token use (deploy/llm-gateway/README.md).

The settings are read from the shipped files, and the per-request guard is run as the gateway
runs it, with a stand-in for `litellm`'s base class, which is not a dependency of this repository.
The stack itself, with the real proxy, is exercised by `deploy/llm-gateway/scripts/smoke_test.sh`.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest
import yaml

GATEWAY = Path(__file__).resolve().parents[2] / "deploy" / "llm-gateway"
CONFIGS = ["config.yaml", "config.test.yaml"]
KEY_LIMITS = ["max_budget", "tpm_limit", "rpm_limit", "max_parallel_requests"]


class ComposeLoader(yaml.SafeLoader):
    """Reads Compose's `!override` tag, which replaces a list instead of adding to it."""


def _override(loader: yaml.SafeLoader, node: yaml.Node) -> list[Any]:
    assert isinstance(node, yaml.SequenceNode)
    return loader.construct_sequence(node, deep=True)


ComposeLoader.add_constructor("!override", _override)


def load(name: str) -> dict[str, Any]:
    text = (GATEWAY / name).read_text(encoding="utf-8")
    document: dict[str, Any] = yaml.load(text, ComposeLoader)  # SafeLoader subclass
    return document


def module_from(path: Path, name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_guard() -> types.ModuleType:
    """dd_token_guard.py with stand-ins for what the gateway's image supplies: litellm's base
    class, and FastAPI's `HTTPException` (carrying the status and detail the proxy reads)."""

    class HTTPError(Exception):
        def __init__(self, status_code: int, detail: str) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    stand_ins: dict[str, types.ModuleType] = {}
    for name in (
        "litellm",
        "litellm.integrations",
        "litellm.integrations.custom_logger",
        "fastapi",
    ):
        stand_ins[name] = types.ModuleType(name)
    stand_ins["litellm.integrations.custom_logger"].CustomLogger = type("CustomLogger", (), {})  # type: ignore[attr-defined]
    stand_ins["fastapi"].HTTPException = HTTPError  # type: ignore[attr-defined]
    saved = {name: sys.modules.get(name) for name in stand_ins}
    sys.modules.update(stand_ins)
    try:
        return module_from(GATEWAY / "dd_token_guard.py", "dd_token_guard_under_test")
    finally:
        for name, before in saved.items():
            if before is None:
                del sys.modules[name]
            else:
                sys.modules[name] = before


GUARD = load_guard()
LIMITS = {"default_max_tokens": 20, "max_output_tokens": 100, "max_input_chars": 3000}


def guarded(data: dict[str, Any], call_type: str = "acompletion") -> dict[str, Any]:
    guard = GUARD.TokenGuard(LIMITS)
    result: dict[str, Any] = asyncio.run(guard.async_pre_call_hook(None, None, data, call_type))
    return result


def refusal(data: dict[str, Any], call_type: str = "acompletion") -> Any:
    with pytest.raises(GUARD.HTTPException) as caught:
        guarded(data, call_type)
    return caught.value


@pytest.mark.parametrize("name", CONFIGS)
def test_the_guard_is_loaded_and_has_limits(name: str) -> None:
    config = load(name)
    assert "dd_token_guard.proxy_handler_instance" in config["litellm_settings"]["callbacks"]
    assert set(config["general_settings"]["dd_token_guard"]) <= set(GUARD.DEFAULTS)
    assert config["general_settings"]["global_max_parallel_requests"] > 0
    assert config["litellm_settings"]["max_budget"] > 0


@pytest.mark.parametrize("name", CONFIGS)
def test_a_key_is_given_a_default_inside_its_ceiling(name: str) -> None:
    settings = load(name)["litellm_settings"]
    defaults = settings["default_key_generate_params"]
    ceiling = settings["upperbound_key_generate_params"]
    for limit in KEY_LIMITS:
        assert 0 < defaults[limit] <= ceiling[limit], limit
    assert defaults["budget_duration"] == ceiling["budget_duration"]


@pytest.mark.parametrize("compose", ["compose.yaml", "compose.test.yaml"])
def test_the_gateway_container_gets_the_guard(compose: str) -> None:
    volumes = load(compose)["services"]["litellm"]["volumes"]
    assert any(v.endswith(":/app/dd_token_guard.py:ro") for v in volumes)


def test_prometheus_loads_the_alert_rules_that_exist() -> None:
    prometheus = load("monitoring/prometheus.yml")
    assert "/etc/prometheus/alerts.yml" in prometheus["rule_files"]
    rules = [r for g in load("monitoring/alerts.yml")["groups"] for r in g["rules"]]
    assert rules
    assert all(r["expr"] and r["labels"]["severity"] for r in rules)


def test_a_request_with_no_output_limit_is_given_the_default() -> None:
    assert guarded({"messages": []})["max_tokens"] == LIMITS["default_max_tokens"]


def test_the_responses_api_is_given_its_own_field() -> None:
    assert guarded({"input": "hi"}, "aresponses")["max_output_tokens"] == 20


def test_a_request_inside_the_limits_is_left_alone() -> None:
    data = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 50}
    assert guarded(dict(data)) == data


def test_an_output_limit_above_the_ceiling_is_refused() -> None:
    error = refusal({"messages": [], "max_tokens": LIMITS["max_output_tokens"] + 1})
    assert error.status_code == 400


def test_the_other_spellings_of_the_output_limit_are_checked_too() -> None:
    assert refusal({"messages": [], "max_completion_tokens": 10_000}).status_code == 400
    assert refusal({"input": "hi", "max_output_tokens": 10_000}, "aresponses").status_code == 400


def test_a_prompt_over_the_ceiling_is_refused() -> None:
    big = {"messages": [{"role": "user", "content": "x" * LIMITS["max_input_chars"]}]}
    assert refusal({**big, "max_tokens": 50}).status_code == 413


def test_an_embedding_or_other_call_is_not_touched() -> None:
    data = {"input": "x" * 100_000}
    assert guarded(dict(data), "aembedding") == data


def test_the_shipped_defaults_cover_what_the_agents_ask_for() -> None:
    # agents/orchestrator-model asks for 16000 output tokens at most.
    assert GUARD.DEFAULTS["max_output_tokens"] >= 16000


def admin_namespace(**given: Any) -> argparse.Namespace:
    fields: dict[str, Any] = {"budget": None, "period": None, "models": None, "unlimited": False}
    return argparse.Namespace(**{**fields, **given})


def test_admin_refuses_a_key_with_no_limits() -> None:
    admin = module_from(GATEWAY / "scripts" / "admin.py", "gateway_admin_under_test")
    with pytest.raises(SystemExit, match="--budget, --period, --models"):
        admin._require_limits(admin_namespace(), models=True)
    with pytest.raises(SystemExit, match="--models"):
        admin._require_limits(admin_namespace(budget=5.0, period="30d"), models=True)


def test_admin_allows_a_team_with_a_budget_and_a_deliberate_exception() -> None:
    admin = module_from(GATEWAY / "scripts" / "admin.py", "gateway_admin_under_test")
    admin._require_limits(admin_namespace(budget=200.0, period="30d"))
    admin._require_limits(admin_namespace(unlimited=True), models=True)

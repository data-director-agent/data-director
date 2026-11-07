"""scripts/check_deploy.py: the Compose stack's agent list and services keep in step with the app's."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_deploy as cd  # noqa: E402

APP = """agents:
  - name: advisor-quality
    url: http://127.0.0.1:8102
  - name: orchestrator-stub
    url: http://127.0.0.1:8106
    timeout_s: 120
"""
COMPOSE_LIST = """agents:
  - name: advisor-quality
    url: http://advisor-quality:8102
  - name: orchestrator-stub
    url: http://orchestrator-stub:8106
    timeout_s: 120
"""
COMPOSE = """services:
  advisor-quality:
    command: uv run --no-sync dd-advisor-quality serve --host 0.0.0.0 --port 8102 --public-url http://advisor-quality:8102
    environment:
      PORT: "8102"
  orchestrator-stub:
    command: uv run --no-sync dd-orchestrator-stub serve --host 0.0.0.0 --port 8106 --public-url http://orchestrator-stub:8106
    environment:
      PORT: "8106"
"""


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def list_problems(tmp_path: Path, compose_list: str) -> list[str]:
    return cd.compose_list_problems(
        write(tmp_path, "app.yaml", APP), write(tmp_path, "agents.yaml", compose_list)
    )


def service_problems(tmp_path: Path, compose: str) -> list[str]:
    return cd.compose_service_problems(
        write(tmp_path, "agents.yaml", COMPOSE_LIST), write(tmp_path, "compose.yaml", compose)
    )


def test_the_repository_passes() -> None:
    assert cd.problems() == []


def test_lists_that_differ_only_in_host_agree(tmp_path: Path) -> None:
    assert list_problems(tmp_path, COMPOSE_LIST) == []
    assert service_problems(tmp_path, COMPOSE) == []


@pytest.mark.parametrize(
    ("compose_list", "expected"),
    [
        # An agent the app lists is missing.
        (COMPOSE_LIST.split("  - name: orchestrator-stub")[0], "no orchestrator-stub"),
        # An agent the app does not list.
        (COMPOSE_LIST + "  - name: extra\n    url: http://extra:9999\n", "extra is not in"),
        # Another port.
        (COMPOSE_LIST.replace(":8102", ":8103"), "is at http://advisor-quality:8103"),
        # A host other than the service's name.
        (COMPOSE_LIST.replace("http://advisor-quality:", "http://quality:"), "not its service"),
        # Another timeout, or none.
        (COMPOSE_LIST.replace("timeout_s: 120", "timeout_s: 60"), "orchestrator-stub has"),
        (COMPOSE_LIST.replace("    timeout_s: 120\n", ""), "orchestrator-stub has"),
    ],
)
def test_drift_in_the_list_is_found(tmp_path: Path, compose_list: str, expected: str) -> None:
    found = list_problems(tmp_path, compose_list)
    assert any(expected in problem for problem in found), found


@pytest.mark.parametrize(
    ("compose", "expected"),
    [
        (COMPOSE.split("  orchestrator-stub:")[0], "no service orchestrator-stub"),
        (COMPOSE.replace('PORT: "8102"', 'PORT: "8103"'), "advisor-quality does not serve on port"),
        (COMPOSE.replace("--port 8102", "--port 8103"), "advisor-quality does not serve on port"),
        (
            COMPOSE.replace("--public-url http://advisor-quality:8102", ""),
            "advisor-quality does not give --public-url",
        ),
    ],
)
def test_drift_in_the_services_is_found(tmp_path: Path, compose: str, expected: str) -> None:
    found = service_problems(tmp_path, compose)
    assert any(expected in problem for problem in found), found


def test_the_five_agent_list_fails(tmp_path: Path) -> None:
    """The list the Compose stack had before it ran every agent (#632) names what it lacks."""
    five = write(
        tmp_path,
        "agents.yaml",
        """agents:
  - name: example-hello
    url: http://example-hello:8101
  - name: advisor-quality
    url: http://advisor-quality:8102
  - name: advisor-standards
    url: http://advisor-standards:8105
  - name: orchestrator-stub
    url: http://orchestrator-stub:8106
    timeout_s: 120
  - name: orchestrator-model
    url: http://orchestrator-model:8107
    timeout_s: 300
""",
    )
    found = cd.compose_list_problems(compose=five)
    for name in ("advisor-files", "advisor-metadata", "advisor-documentation"):
        assert any(f"no {name}," in problem for problem in found), found

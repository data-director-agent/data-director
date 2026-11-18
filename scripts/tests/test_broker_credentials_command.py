"""deploy/broker-credentials.sh: each agent gets a credential, the broker gets only its digest."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "broker-credentials.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("openssl") is None, reason="needs bash and openssl"
)


@pytest.fixture
def etc(tmp_path: Path) -> Path:
    return tmp_path / "etc"


@pytest.fixture
def units(tmp_path: Path) -> Path:
    path = tmp_path / "units"
    path.mkdir()
    return path


def run(etc: Path, units: Path, *agents: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *agents],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "DD_ETC": str(etc), "DD_UNIT_DIR": str(units)},
    )


def listed(etc: Path) -> dict[str, str]:
    path = etc / "credentials" / "model-broker" / "agent-credentials"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def held(etc: Path, agent: str) -> str:
    path = etc / "credentials" / agent / "dd-model-broker-credential"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    return path.read_text()


def test_each_digest_is_that_of_the_credential_the_agent_holds(etc: Path, units: Path) -> None:
    result = run(etc, units, "advisor-standards", "orchestrator-model")
    assert result.returncode == 0, result.stderr
    digests = listed(etc)
    assert set(digests) == {"advisor.standards", "orchestrator.model"}
    for agent, agent_id in (
        ("advisor-standards", "advisor.standards"),
        ("orchestrator-model", "orchestrator.model"),
    ):
        credential = held(etc, agent)
        assert digests[agent_id] == hashlib.sha256(credential.encode()).hexdigest()
        assert credential not in result.stdout + result.stderr


def test_credentials_differ_between_agents(etc: Path, units: Path) -> None:
    run(etc, units, "advisor-standards", "advisor-policy")
    assert held(etc, "advisor-standards") != held(etc, "advisor-policy")


def test_a_second_run_replaces_the_list_and_the_credentials(etc: Path, units: Path) -> None:
    run(etc, units, "advisor-standards", "advisor-policy")
    first = held(etc, "advisor-standards")
    run(etc, units, "advisor-standards")
    assert set(listed(etc)) == {"advisor.standards"}
    assert held(etc, "advisor-standards") != first


def test_an_unknown_or_repeated_agent_changes_nothing(etc: Path, units: Path) -> None:
    for agents in (
        ("advisor-standards", "no-such-agent"),
        ("advisor-standards", "advisor-standards"),
    ):
        result = run(etc, units, *agents)
        assert result.returncode == 1
        assert not (etc / "credentials").exists()


def test_it_needs_an_agent(etc: Path, units: Path) -> None:
    assert run(etc, units).returncode == 2

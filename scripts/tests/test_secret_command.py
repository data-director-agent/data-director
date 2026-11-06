"""deploy/secret.sh and deploy/credentials.sh: an agent's secrets become its credentials drop-in."""

from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SECRET = ROOT / "deploy" / "secret.sh"
LIBRARY = ROOT / "deploy" / "credentials.sh"
KEY = "sk-ant-test-0123456789"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


@pytest.fixture
def etc(tmp_path: Path) -> Path:
    return tmp_path / "etc"


@pytest.fixture
def units(tmp_path: Path) -> Path:
    path = tmp_path / "units"
    path.mkdir()
    return path


def secret(etc: Path, units: Path, *args: str, value: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SECRET), *args],
        input=value,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "DD_ETC": str(etc), "DD_UNIT_DIR": str(units)},
    )


def sync_all(etc: Path, units: Path) -> subprocess.CompletedProcess[str]:
    script = f'source "{LIBRARY}"; sync_all_credentials'
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "CREDENTIALS": str(etc / "credentials"),
            "UNIT_DIR": str(units),
            "AGENTS_DIR": str(ROOT / "deploy" / "agents"),
        },
    )


def dropin(units: Path, agent: str) -> Path:
    return units / f"data-director-agent@{agent}.service.d" / "credentials.conf"


def test_set_stores_the_value_root_only_and_writes_the_dropin(etc: Path, units: Path) -> None:
    result = secret(etc, units, "set", "orchestrator-model", "anthropic-api-key", value=KEY + "\n")
    assert result.returncode == 0, result.stderr
    key = etc / "credentials" / "orchestrator-model" / "anthropic-api-key"
    assert key.read_text() == KEY
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert stat.S_IMODE(key.parent.stat().st_mode) == 0o700
    lines = dropin(units, "orchestrator-model").read_text().splitlines()
    assert "[Service]" in lines
    assert f"LoadCredential=anthropic-api-key:{key}" in lines
    assert "Environment=ANTHROPIC_API_KEY_FILE=anthropic-api-key" in lines
    assert KEY not in result.stdout + result.stderr


def test_every_secret_of_an_agent_is_in_its_dropin(etc: Path, units: Path) -> None:
    secret(etc, units, "set", "advisor-policy", "anthropic-api-key", value=KEY)
    secret(etc, units, "set", "advisor-policy", "fairsharing-password", value="hunter2")
    text = dropin(units, "advisor-policy").read_text()
    assert "Environment=ANTHROPIC_API_KEY_FILE=anthropic-api-key" in text
    assert "Environment=FAIRSHARING_PASSWORD_FILE=fairsharing-password" in text


def test_set_refuses_a_directory_in_the_way(etc: Path, units: Path) -> None:
    # The mistake this command exists to prevent: the key written into a directory of its name.
    (etc / "credentials" / "orchestrator-model" / "anthropic-api-key").mkdir(parents=True)
    result = secret(etc, units, "set", "orchestrator-model", "anthropic-api-key", value=KEY)
    assert result.returncode == 1
    assert "not a regular file" in result.stderr
    assert not dropin(units, "orchestrator-model").exists()


@pytest.mark.parametrize(
    ("agent", "name", "value", "message"),
    [
        ("orchestrator.model", "anthropic-api-key", KEY, "no deployed agent"),
        ("nobody", "anthropic-api-key", KEY, "no deployed agent"),
        ("app", "anthropic-api-key", KEY, "no deployed agent"),
        ("orchestrator-model", "ANTHROPIC_API_KEY", KEY, "lower-case words"),
        ("orchestrator-model", "../key", KEY, "lower-case words"),
        ("orchestrator-model", "anthropic-api-key", "  \n", "no value"),
        ("orchestrator-model", "anthropic-api-key", "a\nb", "more than one line"),
    ],
)
def test_set_refuses_bad_input(
    etc: Path, units: Path, agent: str, name: str, value: str, message: str
) -> None:
    result = secret(etc, units, "set", agent, name, value=value)
    assert result.returncode == 1
    assert message in result.stderr
    assert not list(units.iterdir())


def test_removing_the_last_secret_removes_the_dropin(etc: Path, units: Path) -> None:
    secret(etc, units, "set", "advisor-standards", "anthropic-api-key", value=KEY)
    assert dropin(units, "advisor-standards").exists()
    result = secret(etc, units, "remove", "advisor-standards", "anthropic-api-key")
    assert result.returncode == 0, result.stderr
    assert not dropin(units, "advisor-standards").parent.exists()
    assert not (etc / "credentials" / "advisor-standards").exists()


def test_list_names_each_secret_and_its_variable_never_its_value(etc: Path, units: Path) -> None:
    secret(etc, units, "set", "orchestrator-model", "anthropic-api-key", value=KEY)
    (etc / "credentials" / "advisor-standards" / "anthropic-api-key").mkdir(parents=True)
    result = secret(etc, units, "list")
    assert result.returncode == 0, result.stderr
    assert "ANTHROPIC_API_KEY_FILE" in result.stdout
    assert f"{len(KEY)} bytes" in result.stdout
    assert "PROBLEM: not a regular file" in result.stdout
    assert KEY not in result.stdout


def test_sync_all_leaves_out_what_is_not_a_secret_and_reports_it(etc: Path, units: Path) -> None:
    credentials = etc / "credentials"
    (credentials / "orchestrator-model" / "anthropic-api-key").mkdir(parents=True)
    (credentials / "orchestrator-model" / "anthropic-api-key" / "stdin").write_text(KEY)
    (credentials / "advisor-standards").mkdir()
    (credentials / "advisor-standards" / "anthropic-api-key").write_text(KEY)
    (credentials / "advisor-standards" / "empty-one").write_text("")
    (credentials / "retired-agent").mkdir()
    (credentials / "retired-agent" / "anthropic-api-key").write_text(KEY)
    (credentials / "app").mkdir()
    (credentials / "app" / "orcid-client-secret").write_text("secret")
    stale = dropin(units, "advisor-repository")
    stale.parent.mkdir()
    stale.write_text("[Service]\n")

    result = sync_all(etc, units)

    assert result.returncode == 1
    assert "anthropic-api-key: not a regular file" in result.stderr
    assert "empty-one: empty" in result.stderr
    assert "retired-agent: no deployed agent" in result.stderr
    assert not dropin(units, "orchestrator-model").exists()
    assert "ANTHROPIC_API_KEY_FILE" in dropin(units, "advisor-standards").read_text()
    assert "empty-one" not in dropin(units, "advisor-standards").read_text()
    assert not stale.exists()
    assert not dropin(units, "app").exists()


def test_sync_all_succeeds_quietly_with_no_secrets(etc: Path, units: Path) -> None:
    result = sync_all(etc, units)
    assert result.returncode == 0, result.stderr
    assert not list(units.iterdir())

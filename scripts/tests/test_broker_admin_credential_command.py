"""deploy/broker-admin-credential.sh: the admin service holds the operators' credential for the
model broker's summary, the broker only its digest, and each unit's drop-in loads its own."""

from __future__ import annotations

import hashlib
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "broker-admin-credential.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("openssl") is None, reason="needs bash and openssl"
)


def run(etc: Path, units: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "DD_ETC": str(etc), "DD_UNIT_DIR": str(units)},
    )


def private(path: Path) -> str:
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    return path.read_text()


def test_the_broker_holds_the_digest_of_the_credential_the_admin_service_holds(
    tmp_path: Path,
) -> None:
    etc, units = tmp_path / "etc", tmp_path / "units"
    result = run(etc, units)
    assert result.returncode == 0, result.stderr
    credential = private(etc / "credentials" / "admin" / "model-broker-admin")
    digest = private(etc / "credentials" / "model-broker" / "admin-credential").strip()
    assert digest == hashlib.sha256(credential.encode()).hexdigest()
    assert credential not in result.stdout + result.stderr
    admin = (units / "data-director-admin.service.d" / "model-broker.conf").read_text()
    broker = (units / "data-director-model-broker.service.d" / "admin-credential.conf").read_text()
    assert "LoadCredential=model-broker-admin:" in admin and "DD_ADMIN_BROKER_URL=" in admin
    assert "LoadCredential=admin-credential:" in broker
    assert "DD_BROKER_ADMIN_CREDENTIAL_FILE=admin-credential" in broker


def test_a_second_run_replaces_the_credential_and_remove_takes_it_away(tmp_path: Path) -> None:
    etc, units = tmp_path / "etc", tmp_path / "units"
    run(etc, units)
    first = (etc / "credentials" / "admin" / "model-broker-admin").read_text()
    run(etc, units)
    assert (etc / "credentials" / "admin" / "model-broker-admin").read_text() != first
    assert run(etc, units, "--remove").returncode == 0
    assert not (etc / "credentials" / "admin" / "model-broker-admin").exists()
    assert not (units / "data-director-admin.service.d" / "model-broker.conf").exists()
    assert not (units / "data-director-model-broker.service.d" / "admin-credential.conf").exists()


def test_an_unknown_argument_is_refused(tmp_path: Path) -> None:
    assert run(tmp_path / "etc", tmp_path / "units", "--rotate").returncode != 0

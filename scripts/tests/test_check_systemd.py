"""The systemd unit lint in scripts/check_systemd.sh: the real units pass, a broken one fails."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_systemd.sh"
UNITS = ROOT / "deploy" / "systemd"
BASELINE = ROOT / "deploy" / "systemd-lint-baseline.txt"


def _systemd_version() -> int:
    if shutil.which("systemd-analyze") is None:
        return 0
    out = subprocess.run(
        ["systemd-analyze", "--version"], capture_output=True, text=True, check=False
    ).stdout
    match = re.search(r"systemd (\d+)", out)
    return int(match.group(1)) if match else 0


pytestmark = pytest.mark.skipif(
    _systemd_version() < 250 or shutil.which("uvx") is None,
    reason="needs systemd-analyze 250 or later and uvx",
)


def run(units: Path, baseline: Path = BASELINE) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), str(units), str(baseline)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def units(tmp_path: Path) -> Path:
    """A copy of the real units to damage."""
    target = tmp_path / "units"
    shutil.copytree(UNITS, target)
    return target


def test_the_real_units_pass() -> None:
    result = run(UNITS)
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_bad_restart_value_fails(units: Path) -> None:
    app = units / "data-director-app.service"
    app.write_text(re.sub(r"^Restart=.*$", "Restart=sometimes", app.read_text(), flags=re.M))
    result = run(units)
    assert result.returncode != 0
    assert "systemd-analyze verify" in result.stdout


def test_a_missing_executable_fails(units: Path) -> None:
    app = units / "data-director-app.service"
    app.write_text(
        re.sub(
            r"^ExecStart=(\S+)",
            "ExecStart=/usr/bin/data-director-no-such-tool",
            app.read_text(),
            flags=re.M,
        )
    )
    assert run(units).returncode != 0


def test_a_finding_outside_the_baseline_fails(tmp_path: Path, units: Path) -> None:
    empty = tmp_path / "empty-baseline.txt"
    empty.write_text("# nothing is accepted\n")
    result = run(units, empty)
    assert result.returncode != 0
    assert "not in empty-baseline.txt" in result.stdout


def test_a_stale_baseline_entry_fails(tmp_path: Path) -> None:
    stale = tmp_path / "stale-baseline.txt"
    stale.write_text(BASELINE.read_text() + "data-director-app.service Security.Nothing # gone\n")
    result = run(UNITS, stale)
    assert result.returncode != 0
    assert "Security.Nothing" in result.stdout

"""deploy/restart.sh restarts the agents a few at a time and the app last, so that a deployment does
not start every service at once on a small VM (#1616). A stand-in `systemctl` lists the target's
units from a file and logs each restart."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

RESTART = Path(__file__).resolve().parents[2] / "deploy" / "restart.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

SYSTEMCTL = """#!/usr/bin/env bash
case "$1" in
  list-dependencies) cat "$DD_TEST_UNITS" ;;
  restart) shift; echo "$*" >>"$DD_TEST_LOG" ;;
  *) exit 1 ;;
esac
"""

UNITS = [
    "data-director.target",
    "data-director-app.service",
    "data-director-agent@a.service",
    "data-director-agent@b.service",
    "data-director-agent@c.service",
    "data-director-admin.service",
    "data-director-agent@d.service",
    "data-director-agent@e.service",
    "data-director-workbench.service",
]


def restart(tmp_path: Path, **env: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tool = bin_dir / "systemctl"
    tool.write_text(SYSTEMCTL)
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    (tmp_path / "units").write_text("\n".join(f"  {unit}" for unit in UNITS) + "\n")
    log = tmp_path / "log"
    done = subprocess.run(
        ["bash", str(RESTART)],
        env={
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "DD_TEST_UNITS": str(tmp_path / "units"),
            "DD_TEST_LOG": str(log),
            "DD_RESTART_PAUSE": "0",
            **env,
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    return done, log.read_text().splitlines() if log.exists() else []


def test_agents_restart_in_batches_then_the_rest_and_the_app_last(tmp_path: Path) -> None:
    done, calls = restart(tmp_path, DD_RESTART_BATCH="2")

    assert done.returncode == 0, done.stderr
    agents = [call.split() for call in calls[:3]]
    assert [len(batch) for batch in agents] == [2, 2, 1]
    assert {unit for batch in agents for unit in batch} == {
        f"data-director-agent@{name}.service" for name in "abcde"
    }
    assert set(calls[3].split()) == {
        "data-director-admin.service",
        "data-director-workbench.service",
    }
    assert calls[4:] == ["data-director-app.service"]


def test_a_batch_size_that_is_not_a_number_is_refused(tmp_path: Path) -> None:
    done, calls = restart(tmp_path, DD_RESTART_BATCH="all")

    assert done.returncode == 2
    assert calls == []

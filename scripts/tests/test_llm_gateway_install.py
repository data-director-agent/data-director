"""The LiteLLM gateway's files reach the VM, and the unit's script says so when one is missing."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATEWAY = ROOT / "deploy" / "llm-gateway"
SYSTEMD_SH = GATEWAY / "scripts" / "systemd.sh"


def test_install_copies_every_file_compose_mounts_from_its_directory() -> None:
    mounted = set(
        re.findall(
            r"^\s*- \./([\w.]+(?:\.py|\.yaml)):", (GATEWAY / "compose.yaml").read_text(), re.M
        )
    )
    assert "dd_token_guard.py" in mounted
    installer = (ROOT / "deploy" / "install.sh").read_text()
    for name in mounted:
        assert f"deploy/llm-gateway/{name}" in installer, name


def test_up_refuses_when_the_token_guard_is_not_a_file(tmp_path: Path) -> None:
    here = tmp_path / "lib"
    here.mkdir()
    (here / "systemd.sh").write_text(SYSTEMD_SH.read_text())
    (here / "dd_token_guard.py").mkdir()  # what Docker leaves behind for a missing source
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text("#!/bin/sh\nexit 0\n")
    docker.chmod(0o755)
    result = subprocess.run(
        ["bash", str(here / "systemd.sh"), "up"],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "DD_ETC": str(tmp_path / "etc")},
    )
    assert result.returncode != 0
    assert "dd_token_guard.py" in result.stderr

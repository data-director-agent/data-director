"""The LiteLLM gateway's files reach the VM, and the unit's script says so when one is missing."""

from __future__ import annotations

import ipaddress
import json
import re
import subprocess
from pathlib import Path

import yaml

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


def test_gateway_network_is_pinned_outside_the_ranges_docker_and_campuses_use() -> None:
    compose = yaml.safe_load((GATEWAY / "compose.yaml").read_text())
    subnets = [c["subnet"] for c in compose["networks"]["default"]["ipam"]["config"]]
    assert subnets
    for subnet in subnets:
        # The default in ${DD_GATEWAY_SUBNET:-<default>}.
        match = re.fullmatch(r"\$\{DD_GATEWAY_SUBNET:-([\d./]+)\}", subnet)
        assert match, subnet
        network = ipaddress.ip_network(match.group(1))
        for taken in ("172.16.0.0/12", "192.168.0.0/16"):
            assert not network.overlaps(ipaddress.ip_network(taken)), (network, taken)


def test_install_sets_docker_address_pools_only_when_there_is_no_daemon_json() -> None:
    installer = (ROOT / "deploy" / "install.sh").read_text()
    block = re.search(r'if \[\[ ! -e "\$docker_daemon" \]\]; then(.*?)\n  else\n', installer, re.S)
    assert block, "install.sh does not guard the write of daemon.json"
    pools = json.loads(re.search(r"<<'JSON'\n(.*?)\nJSON\n", block.group(1), re.S).group(1))  # type: ignore[union-attr]
    for key in ("bip", "default-address-pools"):
        assert key in pools


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

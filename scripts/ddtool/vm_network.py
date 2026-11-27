"""The check of `dd.py doctor` on a VM for Docker networks that overlap a range campus networks use.

A Docker bridge whose subnet overlaps a campus range makes the VM route replies for those clients
to the bridge, so they cannot connect (deploy/README.md, "The LiteLLM gateway").
"""

from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass
from typing import Any

import yaml

from ddtool.vm import Done
from ddtool.vm_report import Checks

# Docker's default pools (172.17.0.0/16 onwards, and 192.168.0.0/16) fall in these; a deployment's
# `campus_ranges` replaces them with its institution's own.
DEFAULT_CAMPUS_RANGES = ("172.16.0.0/12", "192.168.0.0/16")
GATEWAY_NETWORK = "data-director-llm-gateway_default"
DAEMON_FIX = (
    'set "bip" and "default-address-pools" in /etc/docker/daemon.json to ranges no campus '
    "network uses, then sudo systemctl restart docker"
)
GATEWAY_FIX = (
    "set DD_GATEWAY_SUBNET in /etc/data-director/llm-gateway.env, then restart "
    "data-director-llm-gateway.service"
)

type Network = ipaddress.IPv4Network


@dataclass(frozen=True)
class Subnet:
    """One subnet on the VM: what holds it, and whether its bridge has a link."""

    name: str
    network: Network
    up: bool


def _json(done: Done) -> Any:
    try:
        return json.loads(done.out) if done.status == 0 else None
    except json.JSONDecodeError:
        return None


def _network(value: str) -> Network | None:
    try:
        return ipaddress.IPv4Network(value, strict=False)
    except ValueError:
        return None


class NetworkChecks(Checks):
    """Docker networks and bridges against the ranges campus networks use."""

    def campus_ranges(self) -> list[Network]:
        """The ranges to keep clear: `campus_ranges` in deployment.yaml, else the private blocks
        Docker allocates from."""
        listed: list[str] = list(DEFAULT_CAMPUS_RANGES)
        path = self.vm.etc / "deployment.yaml"
        if self.system.readable(path):
            try:
                data = yaml.safe_load(self.system.read(path))
            except yaml.YAMLError:
                data = None  # `settings` reports a file that does not parse
            if isinstance(data, dict) and isinstance(data.get("campus_ranges"), list):
                listed = [str(item) for item in data["campus_ranges"]]
        return [n for item in listed if (n := _network(item))]

    def _bridges(self) -> dict[Network, tuple[str, bool]]:
        """Each bridge interface's subnet, with its name and whether its link is up."""
        found = _json(self.system.run("ip", "-json", "-4", "address", "show", "type", "bridge"))
        bridges: dict[Network, tuple[str, bool]] = {}
        for link in found if isinstance(found, list) else []:
            for address in link.get("addr_info") or []:
                network = _network(f"{address.get('local')}/{address.get('prefixlen')}")
                if network:
                    bridges[network] = (str(link.get("ifname")), link.get("operstate") == "UP")
        return bridges

    def _docker_networks(self) -> list[tuple[str, Network]] | None:
        """Each Docker network's name and IPv4 subnets; None when Docker cannot be asked."""
        listed = self.system.run("docker", "network", "ls", "-q")
        if listed.status == 127:
            return []  # no Docker on this VM
        ids = listed.out.split()
        if listed.status != 0:
            self.report.skip("Docker networks (the docker command refused)")
            return None
        found = _json(self.system.run("docker", "network", "inspect", *ids)) if ids else []
        networks: list[tuple[str, Network]] = []
        for entry in found if isinstance(found, list) else []:
            for config in (entry.get("IPAM") or {}).get("Config") or []:
                network = _network(str(config.get("Subnet")))
                if network:
                    networks.append((str(entry.get("Name")), network))
        return networks

    def _subnets(self) -> list[Subnet]:
        bridges = self._bridges()
        subnets: list[Subnet] = []
        for name, network in self._docker_networks() or []:
            # A network whose bridge is not there has no link.
            subnets.append(Subnet(name, network, bridges.pop(network, (name, False))[1]))
        subnets.extend(Subnet(name, network, up) for network, (name, up) in bridges.items())
        return subnets

    def networks(self) -> None:
        """A Docker network or bridge interface whose subnet overlaps a campus range: a problem if
        its link is up, a note if it is down (it clashes once a container starts)."""
        campus = self.campus_ranges()
        for subnet in self._subnets():
            clash = next((c for c in campus if subnet.network.overlaps(c)), None)
            if clash is None:
                continue
            what = f"{subnet.name} has subnet {subnet.network}, which overlaps the campus range {clash}"
            if not subnet.up:
                self.report.note(
                    f"{what}; its link is down, but a container started on it would take replies "
                    f"for clients in that range ({DAEMON_FIX})"
                )
                continue
            fix = DAEMON_FIX
            if subnet.name == GATEWAY_NETWORK:
                fix = f"{GATEWAY_FIX}; and {DAEMON_FIX}"
            self.report.problem(
                f"{what}: the VM routes replies for clients in it to the bridge, so they cannot "
                "connect",
                fix,
            )

"""A VM deployed with deploy/install.sh (deploy/README.md): where it keeps things, and how this
tool reads what systemd, the deployment and the app report.

Every command, file read and request goes through `System`, so that tests can stand in for a VM.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ddtool import paths
from ddtool.common import DevError, parse_env

# How long one command or request may take before it is reported as not answering.
COMMAND_TIMEOUT_S = 30
REQUEST_TIMEOUT_S = 5


@dataclass(frozen=True)
class Vm:
    """Where a VM keeps the deployment. The defaults are deploy/install.sh's."""

    etc: Path = Path("/etc/data-director")
    unit_dir: Path = Path("/etc/systemd/system")
    root: Path = Path("/opt/data-director")
    # The service user's home, and the stores kept in files (deploy/README.md, "Layout on the VM").
    state: Path = Path("/var/lib/data-director")
    # Where backups go unless backup.env says otherwise, and where install.sh puts backup.sh.
    backups: Path = Path("/var/backups/data-director")
    lib: Path = Path("/usr/local/lib/data-director")
    nginx_enabled: Path = Path("/etc/nginx/sites-enabled")
    nginx_available: Path = Path("/etc/nginx/sites-available")
    sudoers: Path = Path("/etc/sudoers.d/data-director")
    app_url: str = "http://127.0.0.1:7860"
    # The clone this tool runs from: deploy/secret.sh and deploy/install.sh are run from it.
    clone: Path = field(default_factory=lambda: paths.ROOT)

    @property
    def current(self) -> Path:
        return self.root / "current"

    @property
    def releases(self) -> Path:
        return self.root / "releases"

    @property
    def bare(self) -> Path:
        return self.root / "repo.git"

    @property
    def failed(self) -> Path:
        return self.root / "failed-commits"

    @property
    def credentials(self) -> Path:
        return self.etc / "credentials"

    @property
    def app_env(self) -> Path:
        return self.etc / "app.env"

    @property
    def agents_env(self) -> Path:
        return self.etc / "agents.env"

    @property
    def deploy_env(self) -> Path:
        return self.etc / "deploy.env"

    @property
    def workbench_env(self) -> Path:
        return self.etc / "workbench.env"

    @property
    def backup_env(self) -> Path:
        return self.etc / "backup.env"

    def agent_env(self, name: str) -> Path:
        return self.etc / "agents" / f"{name}.env"

    def credentials_dropin(self, name: str) -> Path:
        return self.unit_dir / f"data-director-agent@{name}.service.d" / "credentials.conf"

    def live_release(self) -> Path | None:
        """The release `current` points at, or None if there is none."""
        if not self.current.is_symlink() and not self.current.is_dir():
            return None
        return self.current.resolve()

    def source(self) -> Path:
        """Where the deployed configuration is read from: the live release, else the clone."""
        return self.live_release() or self.clone


def agent_unit(name: str) -> str:
    return f"data-director-agent@{name}.service"


@dataclass(frozen=True)
class Done:
    """What a command returned."""

    status: int
    out: str


class System:
    """The VM as this tool sees it: commands, files and HTTP. Tests replace it."""

    def run(self, *cmd: str) -> Done:
        try:
            found = subprocess.run(
                cmd, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_S, check=False
            )
        except FileNotFoundError:
            return Done(127, "")
        except subprocess.TimeoutExpired:
            return Done(124, "")
        return Done(found.returncode, found.stdout + found.stderr)

    def get(self, url: str) -> str | None:
        """The body at `url`, or None if it does not answer with 2xx."""
        try:
            with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_S) as response:
                body: str = response.read().decode("utf-8", errors="replace")
                return body
        except OSError:
            return None

    def is_root(self) -> bool:
        return os.geteuid() == 0

    def readable(self, path: Path) -> bool:
        """Whether `path` is a file this user may read."""
        try:
            return path.is_file() and os.access(path, os.R_OK)
        except OSError:
            return False

    def exists(self, path: Path) -> bool:
        """Whether `path` exists, so far as this user can tell."""
        try:
            return path.exists() or path.is_symlink()
        except OSError:
            return False

    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def disk(self, path: Path) -> tuple[int, int] | None:
        """The size of the file system that holds `path` and the bytes free on it, or None if
        `path` cannot be reached."""
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            return None
        return usage.total, usage.free


def systemctl_show(system: System, units: list[str], props: list[str]) -> dict[str, dict[str, str]]:
    """`systemctl show` for several units at once: each unit's properties, by its name."""
    if not units:
        return {}
    done = system.run("systemctl", "show", *(f"--property={p}" for p in ["Id", *props]), *units)
    shown: dict[str, dict[str, str]] = {}
    block: dict[str, str] = {}
    for line in [*done.out.splitlines(), ""]:
        if not line.strip():
            if "Id" in block:
                shown[block["Id"]] = block
            block = {}
            continue
        key, _, value = line.partition("=")
        block[key] = value
    return shown


def is_active(system: System, unit: str) -> bool:
    return system.run("systemctl", "is-active", "--quiet", unit).status == 0


def agent_instances(system: System) -> list[str]:
    """Every `data-director-agent@` unit systemd knows of, loaded or not."""
    done = system.run(
        "systemctl", "list-units", "--all", "--plain", "--no-legend", "data-director-agent@*"
    )
    return sorted({line.split()[0] for line in done.out.splitlines() if line.strip()})


def wanted_agents(system: System, vm: Vm) -> set[str]:
    """The agents data-director.target starts, from the unit as installed and its drop-ins."""
    files = [vm.unit_dir / "data-director.target"]
    dropins = vm.unit_dir / "data-director.target.d"
    if dropins.is_dir():
        files += sorted(dropins.glob("*.conf"))
    names: set[str] = set()
    for file in files:
        if not system.readable(file):
            continue
        for line in system.read(file).splitlines():
            key, _, value = line.strip().partition("=")
            if key.strip() != "Wants":
                continue
            for unit in value.split():
                if unit.startswith("data-director-agent@") and unit.endswith(".service"):
                    names.add(unit.removeprefix("data-director-agent@").removesuffix(".service"))
    return names


def loaded_secrets(system: System, vm: Vm, name: str) -> set[str]:
    """The secrets an agent's credentials drop-in loads (deploy/credentials.sh writes it)."""
    dropin = vm.credentials_dropin(name)
    if not system.readable(dropin):
        return set()
    return {
        line.partition("=")[2].partition(":")[0]
        for line in system.read(dropin).splitlines()
        if line.startswith("LoadCredential=")
    }


def read_settings(system: System, path: Path) -> dict[str, str] | None:
    """A settings file's variables; {} if there is none, None if this user may not read it."""
    if not system.exists(path):
        return {}
    if not system.readable(path):
        return None
    return parse_env(system.read(path), str(path))


def about(system: System, vm: Vm) -> dict[str, Any] | None:
    """What the app says it runs (`GET /api/about`), or None if it does not answer."""
    body = system.get(f"{vm.app_url}/api/about")
    if body is None:
        return None
    try:
        found = json.loads(body)
    except ValueError:
        return None
    return found if isinstance(found, dict) else None


def domain(system: System, vm: Vm) -> str:
    """The site's name, from the NGINX site install.sh wrote, for the commands doctor suggests."""
    site = vm.nginx_available / "data-director"
    if system.readable(site):
        for line in system.read(site).splitlines():
            words = line.strip().rstrip(";").split()
            if len(words) > 1 and words[0] == "server_name":
                return words[1]
    return "<domain>"


def detect(system: System, vm: Vm) -> bool:
    """Whether this host is a VM deployed with install.sh."""
    return system.exists(vm.etc) and system.exists(vm.root)


def require_vm(system: System, vm: Vm) -> None:
    if not detect(system, vm):
        raise DevError(f"no deployment here ({vm.etc} and {vm.root}); use --target dev")

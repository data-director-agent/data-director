"""The deployment's state: what `data-director doctor` reports, the releases on disk, and each
service's unit and journal (deploy/README.md, "Layout on the VM")."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from dd_admin.settings import AdminSettings
from dd_admin.system import System

# The units every deployment installs (deploy/systemd/); each agent adds its own instance.
FIXED_UNITS = (
    "data-director.target",
    "data-director-app.service",
    "data-director-workbench.service",
    "data-director-admin.service",
    "data-director-deploy.timer",
    "data-director-deploy.service",
    "data-director-restart.path",
    "data-director-backup.timer",
    "data-director-backup.service",
)
UNIT_PROPERTIES = (
    "Id",
    "Description",
    "ActiveState",
    "SubState",
    "UnitFileState",
    "Result",
    "NRestarts",
    "ActiveEnterTimestamp",
)
JOURNAL_LINES = 100
SHA = re.compile(r"[0-9a-f]{7,40}")


def agent_unit(name: str) -> str:
    return f"data-director-agent@{name}.service"


@dataclass(frozen=True)
class DoctorReport:
    """`data-director doctor --json`, or why it could not be had."""

    problems: list[dict[str, str | None]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    target: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    configured: bool = True


def run_doctor(settings: AdminSettings, system: System) -> DoctorReport:
    """Run the doctor and read its report. It exits 1 when it finds a problem, which is a
    report like any other; anything it prints that is not its report is an error."""
    if not settings.doctor:
        return DoctorReport(configured=False)
    done = system.run(*settings.doctor)
    try:
        found = json.loads(done.out)
    except ValueError:
        reason = (done.err or done.out).strip().splitlines()[-1:] or [f"exit {done.status}"]
        return DoctorReport(error=f"the doctor printed no report: {reason[0]}")
    if not isinstance(found, dict):
        return DoctorReport(error="the doctor's report is not a JSON object")
    return DoctorReport(
        problems=[
            {"text": str(p.get("text", "")), "fix": p.get("fix")}
            for p in found.get("problems", [])
            if isinstance(p, dict)
        ],
        notes=[str(n) for n in found.get("notes", [])],
        skipped=[str(s) for s in found.get("skipped", [])],
        target=target if isinstance(target := found.get("target"), dict) else {},
    )


@dataclass(frozen=True)
class Release:
    name: str
    current: bool
    failed: bool
    built: bool


@dataclass(frozen=True)
class Releases:
    """The releases under the deployment root: the live one first, then the rest by name (the
    directory keeps no build time worth trusting), and the commits that failed to start."""

    configured: bool = True
    readable: bool = True
    current: str | None = None
    releases: list[Release] = field(default_factory=list)
    failed_commits: list[str] = field(default_factory=list)


def releases(settings: AdminSettings, system: System) -> Releases:
    root = settings.deploy_root
    if root is None:
        return Releases(configured=False)
    linked = system.resolve(root / "current")
    current = linked.name if linked is not None else None
    failed_text = system.read_text(root / "failed-commits") or ""
    failed = [line.strip() for line in failed_text.splitlines() if SHA.fullmatch(line.strip())]
    entries = system.list_dir(root / "releases")
    if entries is None:
        return Releases(readable=False, current=current, failed_commits=failed)
    found = [
        Release(
            name=entry.name,
            current=entry.name == current,
            failed=entry.name in failed,
            built=system.read_text(entry / ".built") is not None,
        )
        for entry in entries
        if SHA.fullmatch(entry.name)
    ]
    found.sort(key=lambda r: (not r.current, r.name))
    return Releases(current=current, releases=found, failed_commits=failed)


def unit_names(agent_names: list[str]) -> list[str]:
    return [*FIXED_UNITS, *(agent_unit(name) for name in agent_names)]


def unit_states(units: list[str], system: System) -> list[dict[str, str]]:
    """What `systemctl show` says of each unit, in the order given."""
    done = system.run(
        "systemctl", "show", "--no-pager", f"--property={','.join(UNIT_PROPERTIES)}", *units
    )
    if done.status != 0 and not done.out:
        return []
    states: dict[str, dict[str, str]] = {}
    for block in done.out.strip().split("\n\n"):
        props = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        if "Id" in props:
            states[props["Id"]] = props
    return [states.get(unit, {"Id": unit}) for unit in units]


def journal(unit: str, system: System, lines: int = JOURNAL_LINES) -> str:
    """The unit's last `lines` journal lines, or why they cannot be read."""
    done = system.run(
        "journalctl", "--unit", unit, "--lines", str(lines), "--no-pager", "--output", "short-iso"
    )
    if done.status != 0:
        return (done.err or done.out or f"journalctl exited {done.status}").strip()
    return done.out.rstrip()

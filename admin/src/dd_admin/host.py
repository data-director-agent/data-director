"""How hard the machine is working, so an operator sees memory pressure before a workshop does
(docs/guide/operations/admin.md, "Host pressure"; #1616). Read from `/proc` through
`System.read_text`; a file that is missing (not Linux, or no pressure accounting) leaves its
figure unknown. Nothing here writes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dd_admin.system import System

PROC = Path("/proc")

# A figure at or beyond its warning is shown amber; at or beyond its alarm, red.
AVAILABLE_WARN_MB = 600  # the deployment's own floor for starting a build (deploy.sh)
AVAILABLE_ALARM_MB = 300
SWAP_WARN_PERCENT = 50
SWAP_ALARM_PERCENT = 80
LOAD_WARN_PER_CPU = 1.5
LOAD_ALARM_PER_CPU = 4.0


@dataclass(frozen=True)
class HostPressure:
    """Memory, swap and load as the kernel reports them; None where it did not say."""

    memory_total_mb: int | None = None
    memory_available_mb: int | None = None
    swap_total_mb: int | None = None
    swap_used_mb: int | None = None
    load_1m: float | None = None
    load_5m: float | None = None
    cpus: int | None = None
    # Share of the last 60 s in which some task waited for memory (`/proc/pressure/memory`).
    memory_stall_percent: float | None = None

    @property
    def swap_used_percent(self) -> int | None:
        if not self.swap_total_mb or self.swap_used_mb is None:
            return None
        return round(100 * self.swap_used_mb / self.swap_total_mb)

    @property
    def load_per_cpu(self) -> float | None:
        if self.load_1m is None or not self.cpus:
            return None
        return self.load_1m / self.cpus

    @property
    def known(self) -> bool:
        return self.memory_available_mb is not None or self.load_1m is not None

    @property
    def level(self) -> str:
        """`bad`, `warn` or `good`, the worst of the three figures."""
        levels = [
            _level(
                self.memory_available_mb, AVAILABLE_WARN_MB, AVAILABLE_ALARM_MB, low_is_bad=True
            ),
            _level(self.swap_used_percent, SWAP_WARN_PERCENT, SWAP_ALARM_PERCENT),
            _level(self.load_per_cpu, LOAD_WARN_PER_CPU, LOAD_ALARM_PER_CPU),
        ]
        for worst in ("bad", "warn"):
            if worst in levels:
                return worst
        return "good"


def _level(value: float | None, warn: float, alarm: float, *, low_is_bad: bool = False) -> str:
    if value is None:
        return "good"
    if low_is_bad:
        return "bad" if value < alarm else "warn" if value < warn else "good"
    return "bad" if value >= alarm else "warn" if value >= warn else "good"


def meminfo_kb(text: str) -> dict[str, int]:
    """The `Name: value kB` lines of `/proc/meminfo`."""
    found: dict[str, int] = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            found[name] = int(parts[0])
    return found


def _mb(kb: dict[str, int], key: str) -> int | None:
    return kb[key] // 1024 if key in kb else None


def stall_percent(text: str | None) -> float | None:
    """The `some avg60` figure of a pressure file."""
    for line in (text or "").splitlines():
        if line.startswith("some "):
            for part in line.split():
                if part.startswith("avg60="):
                    try:
                        return float(part.removeprefix("avg60="))
                    except ValueError:
                        return None
    return None


def read(system: System, proc: Path = PROC, cpus: int | None = None) -> HostPressure:
    kb = meminfo_kb(system.read_text(proc / "meminfo") or "")
    swap_total = _mb(kb, "SwapTotal")
    swap_free = _mb(kb, "SwapFree")
    load: list[float] = []
    for field in (system.read_text(proc / "loadavg") or "").split()[:2]:
        try:
            load.append(float(field))
        except ValueError:
            break
    return HostPressure(
        memory_total_mb=_mb(kb, "MemTotal"),
        memory_available_mb=_mb(kb, "MemAvailable"),
        swap_total_mb=swap_total,
        swap_used_mb=None if swap_total is None or swap_free is None else swap_total - swap_free,
        load_1m=load[0] if len(load) == 2 else None,
        load_5m=load[1] if len(load) == 2 else None,
        cpus=cpus if cpus is not None else os.cpu_count(),
        memory_stall_percent=stall_percent(system.read_text(proc / "pressure" / "memory")),
    )

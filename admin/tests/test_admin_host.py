"""The host pressure tile (#1616): figures read from /proc, and the level they give."""

from __future__ import annotations

from pathlib import Path

from dd_admin import host
from dd_admin.system import System

MEMINFO = (
    "MemTotal: 3984000 kB\nMemAvailable: 204800 kB\nSwapTotal: 2097152 kB\nSwapFree: 524288 kB\n"
)


class Proc(System):
    def __init__(self, files: dict[str, str]) -> None:
        self.files = files

    def read_text(self, path: Path) -> str | None:
        return self.files.get(path.name)


def test_reads_memory_swap_load_and_stall() -> None:
    system = Proc(
        {
            "meminfo": MEMINFO,
            "loadavg": "70.00 40.00 20.00 1/200 123\n",
            "memory": "some avg10=1.00 avg60=42.50 avg300=3.00 total=1\n",
        }
    )
    found = host.read(system, cpus=2)
    assert found.memory_available_mb == 200
    assert found.swap_used_percent == 75
    assert found.load_per_cpu == 35
    assert found.memory_stall_percent == 42.5
    assert found.level == "bad"


def test_a_machine_that_says_nothing_is_unknown() -> None:
    found = host.read(Proc({}), cpus=2)
    assert not found.known
    assert found.level == "good"


def test_a_quiet_machine_is_good() -> None:
    found = host.read(
        Proc(
            {
                "meminfo": MEMINFO.replace("204800", "2048000").replace(
                    "SwapFree: 524288", "SwapFree: 2097152"
                ),
                "loadavg": "0.10 0.10 0.1 1/1 1",
            }
        ),
        cpus=2,
    )
    assert found.level == "good"

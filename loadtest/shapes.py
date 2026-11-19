"""Load shapes, chosen with LOADTEST_SHAPE (smoke, step or soak; README.md).

- `smoke`: 2 users for a minute. Does the stack answer at all under concurrency?
- `step`: 5, 10, 20, 40 then 80 users, each held for LOADTEST_STEP_SECONDS (default 180). Where
  does latency bend upwards or do errors start: the knee?
- `soak`: LOADTEST_USERS (default 20) for LOADTEST_SOAK_SECONDS (default 3600). Does it stay
  steady, or do memory, connections or locks run out?
"""

from __future__ import annotations

import os

from locust import LoadTestShape

STEPS = (5, 10, 20, 40, 80)


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


class StagedShape(LoadTestShape):
    """Users as a series of (until second, users, spawn rate) stages."""

    def stages(self) -> list[tuple[int, int, float]]:
        shape = os.environ.get("LOADTEST_SHAPE", "smoke")
        if shape == "smoke":
            return [(60, 2, 2.0)]
        if shape == "step":
            hold = _int("LOADTEST_STEP_SECONDS", 180)
            return [(hold * (i + 1), users, 5.0) for i, users in enumerate(STEPS)]
        if shape == "soak":
            users = _int("LOADTEST_USERS", 20)
            return [(_int("LOADTEST_SOAK_SECONDS", 3600), users, 2.0)]
        raise ValueError(f"LOADTEST_SHAPE must be smoke, step or soak, not {shape!r}")

    def tick(self) -> tuple[int, float] | None:
        now = self.get_run_time()  # type: ignore[no-untyped-call]
        for until, users, rate in self.stages():
            if now < until:
                return users, rate
        return None

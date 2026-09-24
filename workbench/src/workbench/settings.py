"""Environment-driven harness settings and the factory that assembles a Conductor.

Only harness concerns live here (where runs go, which profiles directory, whether to write a
crate). Each agent reads its own `DD_<AGENT>_*` variables in its own factory; see env.example.
Kept in one place so the CLI, the transports and the tests build the same object.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from workbench.agents.registry import Registry
from workbench.conductor import Conductor
from workbench.policy import PROFILES_DIR
from workbench.store import RunStore

DEFAULT_RUNS_DIR = Path(__file__).resolve().parents[2] / "runs"


@dataclass(frozen=True)
class Settings:
    runs_dir: Path = DEFAULT_RUNS_DIR
    profiles_dir: Path = PROFILES_DIR
    write_crate: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            runs_dir=Path(os.environ.get("DD_RUNS_DIR", str(DEFAULT_RUNS_DIR))),
            profiles_dir=Path(os.environ.get("DD_PROFILES_DIR", str(PROFILES_DIR))),
            write_crate=os.environ.get("DD_WRITE_CRATE", "1") != "0",
        )


def build_registry(settings: Settings | None = None) -> Registry:
    return Registry.from_entry_points(settings or Settings.from_env())


def build_conductor(settings: Settings | None = None) -> Conductor:
    settings = settings or Settings.from_env()
    return Conductor(
        registry=build_registry(settings),
        store=RunStore(settings.runs_dir),
        profiles_dir=settings.profiles_dir,
        write_crate=settings.write_crate,
    )

"""Environment-driven harness settings and the factory that assembles a Conductor.

Only harness concerns live here (where runs go, which institutional profile governs them,
whether to write a crate, where the agent and source configurations are). Agents are separate
services and read their own `DD_<AGENT>_*` variables in their own processes; see env.example.
Kept in one place so the CLI, the transports and the tests build the same object.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from workbench.conductor import Conductor
from workbench.policy import DEFAULT_PROFILE, load_profile
from workbench.registry import Registry
from workbench.sources import Sources
from workbench.store import RunStore

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_DIR = ROOT / "runs"
DEFAULT_AGENTS_CONFIG = ROOT / "agents.yaml"
DEFAULT_SOURCES_CONFIG = ROOT / "sources.yaml"


@dataclass(frozen=True)
class Settings:
    runs_dir: Path = DEFAULT_RUNS_DIR
    # The one institutional profile this deployment applies to every invocation (ADR-0017).
    profile: Path = DEFAULT_PROFILE
    write_crate: bool = True
    agents_config: Path = DEFAULT_AGENTS_CONFIG
    # The independent copies of sources the source check resolves evidence against (ADR-0016).
    sources_config: Path = DEFAULT_SOURCES_CONFIG
    # The address delegation agents call the workbench back on (ADR-0012). `workbench serve`
    # uses its own host and port when this is unset; set it when agents reach the workbench by
    # another name (a container network, a proxy).
    workbench_url: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            runs_dir=Path(os.environ.get("DD_RUNS_DIR", str(DEFAULT_RUNS_DIR))),
            profile=Path(os.environ.get("DD_PROFILE", str(DEFAULT_PROFILE))),
            write_crate=os.environ.get("DD_WRITE_CRATE", "1") != "0",
            agents_config=Path(os.environ.get("DD_AGENTS_CONFIG", str(DEFAULT_AGENTS_CONFIG))),
            sources_config=Path(os.environ.get("DD_SOURCES_CONFIG", str(DEFAULT_SOURCES_CONFIG))),
            workbench_url=os.environ.get("DD_WORKBENCH_URL") or None,
        )


def build_registry(settings: Settings | None = None) -> Registry:
    return Registry.from_config((settings or Settings.from_env()).agents_config)


def build_conductor(settings: Settings | None = None) -> Conductor:
    settings = settings or Settings.from_env()
    return Conductor(
        registry=build_registry(settings),
        store=RunStore(settings.runs_dir),
        profile=load_profile(settings.profile),  # a bad profile stops start-up, not a request
        write_crate=settings.write_crate,
        sources=Sources.from_config(settings.sources_config),
    )

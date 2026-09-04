"""Environment-driven settings and the factory that assembles a Conductor.

Documented in env.example. Kept in one place so the CLI, the A2A executor and the tests build
the same object.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from workbench.agents.abstain import AbstainingStub
from workbench.agents.base import Agent
from workbench.agents.r3.agent import R3Agent
from workbench.agents.r3.explain import AnthropicExplainer, Explainer, TemplateExplainer
from workbench.agents.r3.fairsharing.live import LiveBackend
from workbench.agents.r3.fairsharing.snapshot import DEFAULT_SNAPSHOT, SnapshotBackend
from workbench.conductor import Conductor
from workbench.policy import PROFILES_DIR
from workbench.store import RunStore

DEFAULT_RUNS_DIR = Path(__file__).resolve().parents[2] / "runs"


@dataclass(frozen=True)
class Settings:
    retrieval: str = "snapshot"  # snapshot | live
    explainer: str = "template"  # template | anthropic
    model_id: str = "claude-opus-5"
    snapshot_path: Path = DEFAULT_SNAPSHOT
    runs_dir: Path = DEFAULT_RUNS_DIR
    profiles_dir: Path = PROFILES_DIR
    write_crate: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            retrieval=os.environ.get("DD_R3_RETRIEVAL", "snapshot"),
            explainer=os.environ.get("DD_R3_EXPLAINER", "template"),
            model_id=os.environ.get("DD_MODEL_ID", "claude-opus-5"),
            snapshot_path=Path(os.environ.get("DD_SNAPSHOT_PATH", str(DEFAULT_SNAPSHOT))),
            runs_dir=Path(os.environ.get("DD_RUNS_DIR", str(DEFAULT_RUNS_DIR))),
            profiles_dir=Path(os.environ.get("DD_PROFILES_DIR", str(PROFILES_DIR))),
            write_crate=os.environ.get("DD_WRITE_CRATE", "1") != "0",
        )


def build_explainer(settings: Settings) -> Explainer:
    if settings.explainer == "anthropic":
        return AnthropicExplainer(model_id=settings.model_id)
    if settings.explainer == "template":
        return TemplateExplainer()
    raise ValueError(f"DD_R3_EXPLAINER={settings.explainer!r}: expected template or anthropic")


def build_r3(settings: Settings) -> R3Agent:
    snapshot = SnapshotBackend(settings.snapshot_path)
    if settings.retrieval == "live":
        return R3Agent(
            retrieval=LiveBackend(), fallback=snapshot, explainer=build_explainer(settings)
        )
    if settings.retrieval == "snapshot":
        return R3Agent(retrieval=snapshot, explainer=build_explainer(settings))
    raise ValueError(f"DD_R3_RETRIEVAL={settings.retrieval!r}: expected snapshot or live")


def build_agents(settings: Settings) -> dict[str, Agent]:
    agents: list[Agent] = [build_r3(settings), AbstainingStub()]
    return {a.agent_id: a for a in agents}


def build_conductor(settings: Settings | None = None) -> Conductor:
    settings = settings or Settings.from_env()
    return Conductor(
        agents=build_agents(settings),
        store=RunStore(settings.runs_dir),
        profiles_dir=settings.profiles_dir,
        write_crate=settings.write_crate,
    )

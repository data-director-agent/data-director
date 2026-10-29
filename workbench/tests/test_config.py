"""The workbench's development configuration (`workbench.config`): the agent list matches the
agent packages, and the committed source copies match their pins and verify real agents'
evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from dd_agent_advisor_standards.agent import StandardsAgent
from dd_agent_advisor_standards.explain import TemplateExplainer
from dd_agent_advisor_standards.fairsharing.snapshot import SnapshotBackend
from dd_harness import testing as fakes
from dd_harness.registry import load_config
from dd_harness.sources import Sources, check
from dd_sdk.contract.models import OpenInput, OutcomeStatus
from workbench.config import (
    DEFAULT_AGENTS_CONFIG,
    DEFAULT_PROFILE,
    DEFAULT_SOURCES_CONFIG,
    WORKBENCH_ROOT,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from devstack.common import load_agents


def test_the_shipped_config_lists_every_agent_package() -> None:
    # agents.yaml holds only URLs; scripts/dev.py starts each agent on the port the app's list
    # names it at, so the two lists must agree.
    root = Path(__file__).resolve().parents[2]
    ports = {int(e["url"].rsplit(":", 1)[1]) for e in load_config(DEFAULT_AGENTS_CONFIG)}
    served = {a.name: a.port for a in load_agents(root / "app" / "config" / "agents.yaml")}
    packages = {d.name for d in (root / "agents").iterdir() if (d / "pyproject.toml").exists()}
    assert (
        set(served)
        == packages
        == {
            "example-hello",
            "advisor-quality",
            "advisor-standards",
            "advisor-policy",
            "advisor-repository",
            "orchestrator-stub",
            "orchestrator-model",
        }
    )
    assert set(served.values()) == ports


@pytest.mark.requirement("DD-EVIDENCE")
def test_the_committed_source_copies_match_their_pins() -> None:
    assert Sources.from_config(DEFAULT_SOURCES_CONFIG).by_snapshot_ref


def _sample(name: str) -> Any:
    return OpenInput.model_validate(
        json.loads((WORKBENCH_ROOT / "samples" / name).read_text(encoding="utf-8"))
    )


@pytest.mark.requirement("DD-EVIDENCE")
def test_real_agents_evidence_verifies_against_the_committed_copies(tmp_path: Path) -> None:
    agent = StandardsAgent(retrieval=SnapshotBackend(), explainer=TemplateExplainer())
    conductor = fakes.make_conductor(tmp_path / "runs", agent, profile=DEFAULT_PROFILE)
    conductor.sources = Sources.from_config(DEFAULT_SOURCES_CONFIG)
    request = fakes.request(agent.spec.agent_id, _sample("soil-chemistry.profile.json"))
    envelope = conductor.invoke(request, acting_for=fakes.TEST_PRINCIPAL)
    assert envelope.outcome.status == OutcomeStatus.SUCCEEDED, envelope.outcome.statement
    report = check(envelope.to_document(), conductor.sources)
    assert report.passed and report.verified > 0 and not report.unresolved

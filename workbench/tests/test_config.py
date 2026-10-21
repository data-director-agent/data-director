"""The workbench's development configuration (`workbench.config`): the agent list matches the
agent packages, and the committed source copies match their pins and verify real agents'
evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from dd_agent_factcheck.agent import FactChecker
from dd_agent_standards.agent import StandardsAgent
from dd_agent_standards.explain import TemplateExplainer
from dd_agent_standards.fairsharing.snapshot import SnapshotBackend
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


def test_the_shipped_config_lists_every_agent_package() -> None:
    # agents.yaml holds only URLs; run-agents.sh maps each package's script to its port.
    root = Path(__file__).resolve().parents[2]
    ports = {int(e["url"].rsplit(":", 1)[1]) for e in load_config(DEFAULT_AGENTS_CONFIG)}
    script = (root / "scripts" / "run-agents.sh").read_text()
    served = {m[0]: int(m[1]) for m in re.findall(r"\[dd-([a-z0-9]+)\]=(\d+)", script)}
    packages = {d.name for d in (root / "agents").iterdir() if (d / "pyproject.toml").exists()}
    assert (
        set(served)
        == packages
        == {"hello", "quality", "factcheck", "stub", "standards", "director"}
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
@pytest.mark.parametrize(
    ("agent", "sample"),
    [
        (
            StandardsAgent(retrieval=SnapshotBackend(), explainer=TemplateExplainer()),
            "soil-chemistry.profile.json",
        ),
        (FactChecker(), "claim.json"),
    ],
    ids=["standards", "fact.checker"],
)
def test_real_agents_evidence_verifies_against_the_committed_copies(
    tmp_path: Path, agent: Any, sample: str
) -> None:
    conductor = fakes.make_conductor(tmp_path / "runs", agent, profile=DEFAULT_PROFILE)
    conductor.sources = Sources.from_config(DEFAULT_SOURCES_CONFIG)
    request = fakes.request(agent.spec.agent_id, _sample(sample))
    envelope = conductor.invoke(request, acting_for=fakes.TEST_PRINCIPAL)
    assert envelope.outcome.status == OutcomeStatus.SUCCEEDED, envelope.outcome.statement
    report = check(envelope.to_document(), conductor.sources)
    assert report.passed and report.verified > 0 and not report.unresolved

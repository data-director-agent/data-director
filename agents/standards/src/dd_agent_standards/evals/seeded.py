"""The standards advisor seeded-defect evaluation, as an Inspect task.

    uv run inspect eval agents/standards/src/dd_agent_standards/evals/seeded.py --model none
    uv run inspect eval agents/standards/src/dd_agent_standards/evals/seeded.py --model none \
        -T agents=workbench/agents.yaml        # the deployed services instead

By default the standards advisor is built in this process from its own environment variables
(`factory.build`), and reached over in-memory A2A. With `agents`, each case goes to the services
that file lists; cases needing a backend the evaluation cannot control there (`backend:
unavailable`) are left out.

The evaluation acts for whoever runs it, named by `DD_PRINCIPAL_ID` and `DD_PRINCIPAL_NAME`
as for any invocation (ADR-0018); it does not start without them.

The task's metadata records what produced the run, so two logs can be told apart: the git
revision, the standards advisor's configuration variables, and the hashes of the ranking rules, the
snapshot and the case file. None of these is covered by `AgentSpec.version`.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml
from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample

from dd_agent_standards.evals.defects import apply_defect
from dd_agent_standards.evals.scorers import expected_recall, no_wrong_recommendations

AGENT_ID = "standards.advisor"
CASES = Path(__file__).with_name("cases.yaml")
CONFIG_VARIABLES = (
    "DD_STANDARDS_RETRIEVAL",
    "DD_STANDARDS_EXPLAINER",
    "DD_MODEL_ID",
    "DD_SNAPSHOT_PATH",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cases(path: Path = CASES) -> list[dict[str, Any]]:
    from dd_agent_standards.testing import SAMPLES

    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    bases = {
        name: json.loads((SAMPLES / file).read_text(encoding="utf-8"))
        for name, file in spec["bases"].items()
    }
    cases: list[dict[str, Any]] = spec["cases"]
    for case in cases:
        case["input"] = apply_defect(case["defect"], bases[case["base"]])
        case.setdefault("backend", "snapshot")
    return cases


def dataset(cases: list[dict[str, Any]]) -> MemoryDataset:
    return MemoryDataset(
        [
            Sample(
                id=case["id"],
                input=json.dumps(case["input"]),
                target=case["expect"]["status"],
                metadata={k: case[k] for k in ("base", "defect", "backend", "expect")},
            )
            for case in cases
        ],
        name="standards-seeded",
    )


def identity(agents: str | None) -> dict[str, Any]:
    from dd_agent_standards.agent import StandardsAgent
    from dd_agent_standards.fairsharing.snapshot import DEFAULT_MANIFEST
    from dd_agent_standards.rank import RANKING_CONFIG
    from workbench.evaluation import git_revision

    ident: dict[str, Any] = {
        "agent_id": AGENT_ID,
        "git_revision": git_revision(Path(__file__).parent),
        "cases_sha256": _sha256(CASES),
    }
    if agents:
        # The services' own configuration is not visible from here; the envelopes carry what
        # they report (agent_version, snapshot_ref, model_id).
        ident["agents"] = agents
        return ident
    ident |= {
        "spec_version": StandardsAgent.spec.version,
        "configuration": {v: os.environ[v] for v in CONFIG_VARIABLES if v in os.environ},
        "ranking_sha256": _sha256(RANKING_CONFIG),
        "snapshot_sha256": json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))["sha256"],
    }
    return ident


def conductors(agents: str | None) -> Any:
    """A `ConductorFor`: one conductor per backend, built on first use."""
    built: dict[str, Any] = {}
    runs = Path(tempfile.mkdtemp(prefix="dd-eval-standards-"))

    def local(backend: str) -> Any:
        from dd_agent_standards.agent import StandardsAgent
        from dd_agent_standards.explain import TemplateExplainer
        from dd_agent_standards.factory import build
        from dd_agent_standards.testing import FakeRetrieval
        from workbench.config import DEFAULT_PROFILE
        from workbench.testing import make_conductor

        if backend == "snapshot":
            agent = build()
        elif backend == "unavailable":
            agent = StandardsAgent(
                retrieval=FakeRetrieval(unavailable=True), explainer=TemplateExplainer()
            )
        else:
            raise ValueError(f"backend {backend!r}: expected snapshot or unavailable")
        return make_conductor(runs / backend, agent, profile=DEFAULT_PROFILE)

    def remote() -> Any:
        from dd_harness.conductor import Conductor
        from dd_harness.policy import load_profile
        from dd_harness.registry import Registry
        from dd_harness.store import RunStore
        from workbench.config import DEFAULT_PROFILE

        return Conductor(
            registry=Registry.from_config(Path(str(agents))),
            store=RunStore(runs / "remote"),
            profile=load_profile(DEFAULT_PROFILE),
            write_crate=False,
        )

    def conductor_for(case: dict[str, Any]) -> Any:
        key = "remote" if agents else case["backend"]
        if key not in built:
            built[key] = remote() if agents else local(key)
        return built[key]

    return conductor_for


@task
def standards_seeded(agents: str | None = None) -> Task:
    from workbench.config import settings_from_env
    from workbench.evaluation import (
        grounding_passed,
        invoke_agent,
        outcome_matches,
        stopped_correctly,
    )

    cases = load_cases()
    if agents:
        cases = [c for c in cases if c["backend"] == "snapshot"]
    return Task(
        dataset=dataset(cases),
        solver=invoke_agent(conductors(agents), AGENT_ID, settings_from_env().principal()),
        scorer=[
            outcome_matches(),
            stopped_correctly(),
            grounding_passed(),
            expected_recall(),
            no_wrong_recommendations(),
        ],
        metadata={"identity": identity(agents)},
    )

"""The repository advisor's evaluation, as an Inspect task: whether the repositories a confirmed
data management plan names reach the researcher as the plan's, beside the shortlist or without
one (#1334).

    uv run inspect eval ${SHORTLIST} --model none
    uv run inspect eval ${SHORTLIST} --model none \\
        -T agents=workbench/agents.yaml        # the deployed services instead

where `SHORTLIST` is `agents/advisor-repository/src/dd_agent_advisor_repository/evals/shortlist.py`.

By default the advisor is built in this process from its own environment variables
(`factory.build`), with the template explainer unless `DD_REPOSITORY_EXPLAINER` asks for a model,
and reached over in-memory A2A. It reads re3data from the registry built from the pinned export
(`uv run dd-sources prepare`), and FAIRsharing from the committed snapshot.

Each case is sent as a caller outside a project would send it: the commitments a researcher
confirmed in `project_decisions`. In a project the conductor fills them from the project's
decisions; outside one it leaves them as sent (`dd_harness.project_facts`).

Whoever runs the evaluation is the principal each case is invoked for (`DD_PRINCIPAL_ID`,
`DD_PRINCIPAL_NAME`; docs/specs/policy-and-identity.md). The run records the git revision, the
advisor's version and configuration variables, and hashes of the cases, the ranking rules, the
other names for repositories and the pinned re3data registry.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml
from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset

from dd_agent_advisor_repository import registry
from dd_agent_advisor_repository.agent import RepositoryAgent
from dd_agent_advisor_repository.evals.scorers import plan_repositories_shown, shortlist_kept

AGENT_ID = "advisor.repository"
HERE = Path(__file__).parent
CASES = HERE / "cases.yaml"
PACKAGE = HERE.parent
CONFIG_VARIABLES = ("DD_REPOSITORY_EXPLAINER", "DD_REPOSITORY_RETRIEVAL", "DD_MODEL_ID")


def commitment(entry: dict[str, str], quote: str) -> dict[str, Any]:
    """A commitment of the plan as a researcher confirmed it, as a `sharing_commitment` fact."""
    return {
        "fact_kind": "sharing_commitment",
        "fact_subject": entry["subject"],
        "commitment_repository": entry["repository"],
        "commitment_access": "open",
        "commitment_licence": "CC BY 4.0",
        "commitment_quote": " ".join(quote.split()),
        "commitment_document": hashlib.sha256(b"grant/dmp.md").hexdigest(),
    }


def load_cases(path: Path = CASES) -> list[dict[str, Any]]:
    """The cases, each with its input."""
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = spec["cases"]
    for case in cases:
        decisions = [
            commitment(e, spec["quote"]) for e in spec["plan"].get(case.get("commitments"), [])
        ]
        case["input"] = {
            "schema_class": "RepositoryNeeds",
            **spec["bases"][case["base"]],
            "project_decisions": decisions,
        }
    return cases


def dataset(cases: list[dict[str, Any]]) -> MemoryDataset:
    from workbench.evaluation import case_dataset

    return case_dataset(cases, ("base", "expect"), "repository-shortlist")


def identity(agents: str | None) -> dict[str, Any]:
    from workbench.evaluation import configuration, sha256_of, task_identity

    hashes = {
        "cases_sha256": sha256_of(CASES),
        "ranking_sha256": sha256_of(PACKAGE / "ranking.yaml"),
        "aliases_sha256": sha256_of(PACKAGE / "aliases.yaml"),
        "re3data_snapshot_sha256": json.loads(registry.MANIFEST.read_text(encoding="utf-8"))[
            "snapshot_sha256"
        ],
    }
    return task_identity(
        AGENT_ID,
        HERE,
        hashes,
        agents,
        lambda: {
            "spec_version": RepositoryAgent.spec.version,
            "configuration": configuration(CONFIG_VARIABLES),
        },
    )


def advisor() -> RepositoryAgent:
    """The advisor evaluated in this process: as its own configuration builds it, except that the
    evaluation calls no model unless `DD_REPOSITORY_EXPLAINER` asks for one (invariant 1 of the
    evaluation spec), although the advisor's own default is `model`."""
    from dd_agent_advisor_repository.factory import build

    return build({"DD_REPOSITORY_EXPLAINER": "template", **os.environ})


@task
def repository_shortlist(agents: str | None = None) -> Task:
    from workbench.config import settings_from_env
    from workbench.evaluation import (
        grounding_passed,
        invoke_agent,
        one_conductor,
        outcome_matches,
        stopped_correctly,
    )

    agent = None if agents else advisor()
    return Task(
        dataset=dataset(load_cases()),
        solver=invoke_agent(
            one_conductor(lambda: agent, agents, "dd-eval-repository-"),
            AGENT_ID,
            settings_from_env().principal(),
        ),
        scorer=[
            outcome_matches(),
            stopped_correctly(),
            grounding_passed(),
            plan_repositories_shown(),
            shortlist_kept(),
        ],
        metadata={"identity": identity(agents)},
    )

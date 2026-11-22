"""The Rights and Licensing Adviser's evaluation, as an Inspect task: whether the licences and
access levels it offers are those a data steward would list for a reuse wish, a mandate, sensitive
data or third-party content, nothing it should not offer, and the questions it must ask.

    uv run inspect eval ${CHOOSING} --model none
    uv run inspect eval ${CHOOSING} --model none \\
        -T agents=workbench/agents.yaml        # the deployed services instead

where `CHOOSING` is `agents/advisor-rights/src/dd_agent_advisor_rights/evals/choosing.py`.

By default the adviser is built in this process from its own environment variables
(`factory.build`), with the template interpreter unless `DD_RIGHTS_INTERPRETER` asks for a model,
and reached over in-memory A2A. The workbench's profile grants it no `spdx` tool server, so it
reads its packaged table.

Whoever runs the evaluation is the principal each case is invoked for (`DD_PRINCIPAL_ID`,
`DD_PRINCIPAL_NAME`; docs/specs/policy-and-identity.md). The run records the git revision, the
adviser's version and configuration variables, and hashes of the cases, the licence table and the
interpreter's system prompt.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset

from dd_agent_advisor_rights.agent import RightsAdviser
from dd_agent_advisor_rights.evals.scorers import access_first, questions_asked

AGENT_ID = "advisor.rights"
HERE = Path(__file__).parent
CASES = HERE / "cases.yaml"
PACKAGE = HERE.parent
CONFIG_VARIABLES = ("DD_RIGHTS_INTERPRETER", "DD_MODEL_PROVIDER", "DD_MODEL_ID")


def load_cases(path: Path = CASES) -> list[dict[str, Any]]:
    """The cases, each with its input as a `RightsContext` document."""
    cases: list[dict[str, Any]] = yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        case["input"] = {"schema_class": "RightsContext", **case["input"]}
    return cases


def dataset(cases: list[dict[str, Any]]) -> MemoryDataset:
    from workbench.evaluation import case_dataset

    return case_dataset(cases, ("expect",), "rights-choosing")


def identity(agents: str | None) -> dict[str, Any]:
    from workbench.evaluation import configuration, sha256_of, task_identity

    hashes = {
        "cases_sha256": sha256_of(CASES),
        "licences_sha256": sha256_of(PACKAGE / "licences.yaml"),
        "system_prompt_sha256": sha256_of(PACKAGE / "system_prompt.md"),
    }
    return task_identity(
        AGENT_ID,
        HERE,
        hashes,
        agents,
        lambda: {
            "spec_version": RightsAdviser.spec.version,
            "configuration": configuration(CONFIG_VARIABLES),
        },
    )


def adviser() -> RightsAdviser:
    """The adviser evaluated in this process: as its own configuration builds it, except that the
    evaluation calls no model unless `DD_RIGHTS_INTERPRETER` asks for one (invariant 1 of the
    evaluation spec), although the adviser's own default is `model`."""
    from dd_agent_advisor_rights.factory import build

    return build({"DD_RIGHTS_INTERPRETER": "template", **os.environ})


@task
def rights_choosing(agents: str | None = None) -> Task:
    from workbench.config import settings_from_env
    from workbench.evaluation import (
        grounding_passed,
        ids_recalled,
        invoke_agent,
        none_listed,
        one_conductor,
        outcome_matches,
        stopped_correctly,
    )

    agent = None if agents else adviser()
    return Task(
        dataset=dataset(load_cases()),
        solver=invoke_agent(
            one_conductor(lambda: agent, agents, "dd-eval-rights-"),
            AGENT_ID,
            settings_from_env().principal(),
        ),
        scorer=[
            outcome_matches(),
            stopped_correctly(),
            grounding_passed(),
            ids_recalled("licences", "spdx_id"),
            none_listed("licences", "spdx_id"),
            access_first(),
            questions_asked(),
        ],
        metadata={"identity": identity(agents)},
    )

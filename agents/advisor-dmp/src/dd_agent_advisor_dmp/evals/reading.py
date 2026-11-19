"""The Data Management Plan Checker's evaluation, as an Inspect task: reading a free-text plan's
sharing commitments, and comparing the ones a researcher confirmed (#962).

    uv run inspect eval ${READING} --model none
    uv run inspect eval ${READING} --model none \
        -T agents=workbench/agents.yaml        # the deployed services instead

where `READING` is `agents/advisor-dmp/src/dd_agent_advisor_dmp/evals/reading.py`.

By default the checker is built in this process from its own environment variables
(`factory.build`), so `DD_DMP_MATCHER` chooses the template path (the evaluation's default,
though not the checker's) or a model, and reached over in-memory A2A. `--model none` is right
either way: Inspect calls no model, and any model the checker calls is its own. On the template
path a plan is not read, so the reading cases expect the checker to say so; with a model they
expect it to read. With `agents`, each case goes to the services that file lists, which are
taken to have a model.

Each case is sent as a caller outside a project would send it: the plan in `project_documents`,
and the commitments a researcher confirmed in `project_decisions`. In a project the conductor
fills both from the project's own attachments and decisions; outside one it leaves them as sent
(`dd_harness.project_facts`).

The evaluation acts for whoever runs it, named by `DD_PRINCIPAL_ID` and `DD_PRINCIPAL_NAME` as for
any invocation (docs/specs/policy-and-identity.md); it does not start without them.

The task's metadata records what produced the run: the git revision, the checker's configuration
variables and version, and the hashes of the case file, the reading prompt and the plans.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset

from dd_agent_advisor_dmp.agent import DmpChecker
from dd_agent_advisor_dmp.evals.scorers import (
    aspects_agree,
    discrepancies_match,
    no_unlabelled_commitment,
    outputs_recalled,
    quotes_found,
)
from dd_agent_advisor_dmp.read_plan import TemplateReader

AGENT_ID = "advisor.dmp"
HERE = Path(__file__).parent
CASES = HERE / "cases.yaml"
DATA = HERE / "data"
PROMPT = HERE.parent / "read_prompt.md"
CONFIG_VARIABLES = ("DD_DMP_MATCHER", "DD_MODEL_PROVIDER", "DD_MODEL_ID")
# When the plans were attached, as the conductor would record it. Fixed, so the input hash is.
ATTACHED = datetime(2026, 11, 1, tzinfo=UTC)
ASPECTS = ("repository", "access", "licence")


def document(file: str) -> dict[str, Any]:
    """A plan in data/ as a `ProjectDocument`, as the conductor gives an attached one."""
    text = (DATA / file).read_text(encoding="utf-8")
    return {
        "documentation_name": file,
        "documentation_digest": hashlib.sha256(text.encode()).hexdigest(),
        "documentation_media_type": "text/markdown",
        "documentation_size": len(text.encode()),
        "documentation_added_at": ATTACHED.isoformat(),
        "documentation_text": text,
    }


def decision(
    label: dict[str, Any], plan: dict[str, Any], correction: dict[str, Any]
) -> dict[str, Any]:
    """A labelled commitment as a researcher confirmed it, with any correction they made, as a
    `sharing_commitment` project fact."""
    value = {aspect: correction.get(aspect, label[aspect]) for aspect in ASPECTS}
    return {
        "fact_kind": "sharing_commitment",
        "fact_subject": label["output"],
        **{f"commitment_{aspect}": v for aspect, v in value.items()},
        "commitment_quote": " ".join(label["quote"].split()),
        "commitment_document": plan["documentation_digest"],
    }


def load_cases(path: Path = CASES, *, reads: bool = True) -> list[dict[str, Any]]:
    """The cases, each with its input. `reads` says whether the checker evaluated reads a plan;
    where it does not, a case's `template` outcome is the one expected."""
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    plans = spec["plans"]
    cases: list[dict[str, Any]] = spec["cases"]
    for case in cases:
        plan = plans[case["plan"]]
        attached = document(plan["file"])
        case["kind"] = "compare" if "planned" in case else "read"
        case["labels"] = plan["commitments"]
        case["documents"] = {attached["documentation_digest"]: attached["documentation_text"]}
        if not reads and "template" in case:
            case["expect"] = {**case["expect"], **case["template"]}
        if case["kind"] == "read":
            case["input"] = {"schema_class": "DmpCommitments", "project_documents": [attached]}
            continue
        corrections = case.get("corrections", {})
        case["input"] = {
            "schema_class": "DmpCommitments",
            "project_decisions": [
                decision(label, attached, corrections.get(label["output"], {}))
                for label in plan["commitments"]
            ],
            "planned_outputs": case["planned"],
        }
    return cases


def dataset(cases: list[dict[str, Any]]) -> MemoryDataset:
    from workbench.evaluation import case_dataset

    keys = ("plan", "kind", "expect", "labels", "documents")
    return case_dataset(cases, keys, "dmp-reading")


def identity(agents: str | None) -> dict[str, Any]:
    from workbench.evaluation import configuration, sha256_of, task_identity

    hashes = {
        "cases_sha256": sha256_of(CASES),
        "read_prompt_sha256": sha256_of(PROMPT),
        "data_sha256": {p.name: sha256_of(p) for p in sorted(DATA.glob("*.md"))},
    }
    return task_identity(
        AGENT_ID,
        HERE,
        hashes,
        agents,
        lambda: {
            "spec_version": DmpChecker.spec.version,
            "configuration": configuration(CONFIG_VARIABLES),
        },
    )


def checker() -> DmpChecker:
    """The checker evaluated in this process: as its own configuration builds it, except that the
    evaluation calls no model unless `DD_DMP_MATCHER` asks for one (invariant 1 of the evaluation
    spec), although the checker's own default is `model`. A test may replace this to evaluate a
    checker with a fake model."""
    from dd_agent_advisor_dmp.factory import build

    return build({"DD_DMP_MATCHER": "template", **os.environ})


@task
def dmp_reading(agents: str | None = None) -> Task:
    from workbench.config import settings_from_env
    from workbench.evaluation import (
        grounding_passed,
        invoke_agent,
        one_conductor,
        outcome_matches,
        stopped_correctly,
    )

    agent = None if agents else checker()
    reads = agent is None or not isinstance(agent.reader, TemplateReader)
    return Task(
        dataset=dataset(load_cases(reads=reads)),
        solver=invoke_agent(
            one_conductor(lambda: agent, agents, "dd-eval-dmp-"),
            AGENT_ID,
            settings_from_env().principal(),
        ),
        scorer=[
            outcome_matches(),
            stopped_correctly(),
            grounding_passed(),
            outputs_recalled(),
            aspects_agree(),
            no_unlabelled_commitment(),
            quotes_found(),
            discrepancies_match(),
        ],
        metadata={"identity": identity(agents)},
    )

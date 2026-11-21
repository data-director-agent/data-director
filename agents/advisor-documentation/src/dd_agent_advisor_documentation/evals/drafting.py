"""The Documentation Editor's evaluation, as an Inspect task.

    uv run inspect eval ${DRAFTING} --model none
    uv run inspect eval ${DRAFTING} --model none \
        -T agents=workbench/agents.yaml        # the deployed services instead

where `DRAFTING` is
`agents/advisor-documentation/src/dd_agent_advisor_documentation/evals/drafting.py`.

By default the editor is built in this process from its own environment variables
(`factory.build`), so `DD_DOCUMENTATION_WRITER` chooses the template path (the evaluation's
default, though not the editor's) or a model, and reached over in-memory A2A. `--model none` is
right either way: Inspect calls no model, and any model the editor calls is its own. With
`agents`, each case goes to the services that file lists.

The evaluation acts for whoever runs it, named by `DD_PRINCIPAL_ID` and `DD_PRINCIPAL_NAME` as for
any invocation (docs/specs/policy-and-identity.md); it does not start without them.

The task's metadata records what produced the run: the git revision, the editor's configuration
variables and version, and the hashes of the case file, the README template and the data files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset

from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_documentation.dictionary import _question_id
from dd_agent_advisor_documentation.evals.defects import apply_defect
from dd_agent_advisor_documentation.evals.scorers import (
    answers_placed_supplied,
    every_cell_sourced,
    every_gap_marked_and_asked,
    expected_content_present,
    inferred_types_match_gold,
    no_model_value_in_cell,
    no_unsupported_claim,
    required_sections_present,
    suggestions_match_gold,
    unknown_cells_asked,
)
from dd_agent_advisor_documentation.sections import README

AGENT_ID = "advisor.documentation"
HERE = Path(__file__).parent
CASES = HERE / "cases.yaml"
DATA = HERE / "data"
CONFIG_VARIABLES = ("DD_DOCUMENTATION_WRITER", "DD_MODEL_PROVIDER", "DD_MODEL_ID")
# What a base takes from its request: the rest is the case's to set.
BASE_KEYS = ("inventory", "requirements", "metadata_record")
# The version a README case redrafts, unless the case is `first`: the note the first run left
# when it asked what the README needs (docs/specs/drafting.md), so that the case scores the
# README itself.
ASKED_FIRST = {
    "version_ref": {"document_id": "01900000-0000-7000-8000-000000000001", "version": 1},
    "document_title": "README",
    "media_type": "text/markdown",
    "document_text": "# README\n\n_This is not the README yet._\n",
    "version_state": "proposed",
}


def _read(name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((DATA / name).read_text(encoding="utf-8"))
    return document


def base_request(spec: dict[str, Any]) -> dict[str, Any]:
    """A base's inventory, requirements and metadata record, as a `DraftRequest` document with no
    kind yet."""
    request = _read(spec["request"])
    base = {"schema_class": "DraftRequest"} | {k: request[k] for k in BASE_KEYS if k in request}
    for key in ("inventory", "metadata_record"):
        if key in spec:
            base[key] = _read(spec[key])
    return base


def answer_target(answer: dict[str, Any]) -> dict[str, str]:
    """The gap an answer fills, in the form the editor derives its question identifier from."""
    if "column" in answer:
        return {k: answer[k] for k in ("file", "field", "column")}
    return {k: answer[k] for k in ("section", "part") if k in answer}


def load_cases(path: Path = CASES) -> list[dict[str, Any]]:
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    bases = {name: base_request(b) for name, b in spec["bases"].items()}
    cases: list[dict[str, Any]] = spec["cases"]
    for case in cases:
        answers = [
            a | {"question_id": _question_id(answer_target(a))} for a in case.get("answers", [])
        ]
        request = apply_defect(case["defect"], bases[case["base"]]) | {
            "document_kind": case["kind"],
            "draft_answers": [
                {"answered_question": a["question_id"], "answer_text": a["text"]} for a in answers
            ],
        }
        if case["kind"] == "readme" and not case.get("first"):
            request["current_version"] = ASKED_FIRST
        case["answers"] = answers
        case["input"] = request
        case["gold"] = spec.get("gold", {}).get(case["base"], {})
    return cases


def dataset(cases: list[dict[str, Any]]) -> MemoryDataset:
    from workbench.evaluation import case_dataset

    keys = ("base", "kind", "defect", "expect", "answers", "gold")
    return case_dataset(cases, keys, "documentation-drafting")


def identity(agents: str | None) -> dict[str, Any]:
    from workbench.evaluation import configuration, sha256_of, task_identity

    hashes = {
        "cases_sha256": sha256_of(CASES),
        "readme_template_sha256": sha256_of(README),
        "data_sha256": {p.name: sha256_of(p) for p in sorted(DATA.glob("*.json"))},
    }
    return task_identity(
        AGENT_ID,
        HERE,
        hashes,
        agents,
        lambda: {
            "spec_version": DocumentationEditor.spec.version,
            "configuration": configuration(CONFIG_VARIABLES),
        },
    )


def editor() -> DocumentationEditor:
    """The editor evaluated in this process: as its own configuration builds it, except that the
    evaluation calls no model unless `DD_DOCUMENTATION_WRITER` asks for one (invariant 1 of the
    evaluation spec), although the editor's own default is `model`. A test may replace this to
    evaluate an editor with a fake model."""
    from dd_agent_advisor_documentation.factory import build

    return build({"DD_DOCUMENTATION_WRITER": "template", **os.environ})


def conductors(agents: str | None) -> Any:
    """A `ConductorFor`: one conductor for every case, built on first use."""
    from workbench.evaluation import one_conductor

    return one_conductor(lambda: editor(), agents, "dd-eval-documentation-")


@task
def documentation_drafting(agents: str | None = None) -> Task:
    from workbench.config import settings_from_env
    from workbench.evaluation import (
        grounding_passed,
        invoke_agent,
        outcome_matches,
        stopped_correctly,
    )

    return Task(
        dataset=dataset(load_cases()),
        solver=invoke_agent(conductors(agents), AGENT_ID, settings_from_env().principal()),
        scorer=[
            outcome_matches(),
            stopped_correctly(),
            grounding_passed(),
            every_cell_sourced(),
            no_model_value_in_cell(),
            unknown_cells_asked(),
            inferred_types_match_gold(),
            suggestions_match_gold(),
            required_sections_present(),
            every_gap_marked_and_asked(),
            expected_content_present(),
            no_unsupported_claim(),
            answers_placed_supplied(),
        ],
        metadata={"identity": identity(agents)},
    )

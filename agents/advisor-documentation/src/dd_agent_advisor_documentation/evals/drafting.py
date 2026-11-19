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

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

import yaml
from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample

from dd_agent_advisor_documentation.agent import DocumentationEditor
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
from dd_agent_advisor_documentation.gaps import question_id as _question_id
from dd_agent_advisor_documentation.sections import README

AGENT_ID = "advisor.documentation"
HERE = Path(__file__).parent
CASES = HERE / "cases.yaml"
DATA = HERE / "data"
CONFIG_VARIABLES = ("DD_DOCUMENTATION_WRITER", "DD_MODEL_PROVIDER", "DD_MODEL_ID")
# What a base takes from its request: the rest is the case's to set.
BASE_KEYS = ("inventory", "requirements", "metadata_record")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        case["answers"] = answers
        case["input"] = request
        case["gold"] = spec.get("gold", {}).get(case["base"], {})
    return cases


def dataset(cases: list[dict[str, Any]]) -> MemoryDataset:
    return MemoryDataset(
        [
            Sample(
                id=case["id"],
                input=json.dumps(case["input"]),
                target=case["expect"]["status"],
                metadata={
                    k: case[k] for k in ("base", "kind", "defect", "expect", "answers", "gold")
                },
            )
            for case in cases
        ],
        name="documentation-drafting",
    )


def identity(agents: str | None) -> dict[str, Any]:
    from workbench.evaluation import git_revision

    ident: dict[str, Any] = {
        "agent_id": AGENT_ID,
        "git_revision": git_revision(HERE),
        "cases_sha256": _sha256(CASES),
        "readme_template_sha256": _sha256(README),
        "data_sha256": {p.name: _sha256(p) for p in sorted(DATA.glob("*.json"))},
    }
    if agents:
        # The services' own configuration is not visible from here; the envelopes carry what they
        # report (agent_version, model_id).
        ident["agents"] = agents
        return ident
    ident |= {
        "spec_version": DocumentationEditor.spec.version,
        "configuration": {v: os.environ[v] for v in CONFIG_VARIABLES if v in os.environ},
    }
    return ident


def editor() -> DocumentationEditor:
    """The editor evaluated in this process: as its own configuration builds it, except that the
    evaluation calls no model unless `DD_DOCUMENTATION_WRITER` asks for one (invariant 1 of the
    evaluation spec), although the editor's own default is `model`. A test may replace this to
    evaluate an editor with a fake model."""
    from dd_agent_advisor_documentation.factory import build

    return build({"DD_DOCUMENTATION_WRITER": "template", **os.environ})


def conductors(agents: str | None) -> Any:
    """A `ConductorFor`: one conductor for every case, built on first use."""
    built: list[Any] = []
    building = threading.Lock()  # cases run side by side; the conductor is built once
    runs = Path(tempfile.mkdtemp(prefix="dd-eval-documentation-"))

    def build() -> Any:
        from dd_harness.conductor import Conductor
        from dd_harness.policy import load_profile
        from dd_harness.registry import Registry
        from dd_harness.store import RunStore
        from dd_harness.testing import make_conductor
        from workbench.config import DEFAULT_PROFILE

        if not agents:
            return make_conductor(runs / "local", editor(), profile=DEFAULT_PROFILE)
        return Conductor(
            registry=Registry.from_config(Path(agents)),
            store=RunStore(runs / "remote"),
            profile=load_profile(DEFAULT_PROFILE),
            write_crate=False,
        )

    def conductor_for(case: dict[str, Any]) -> Any:
        with building:
            if not built:
                built.append(build())
            return built[0]

    return conductor_for


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

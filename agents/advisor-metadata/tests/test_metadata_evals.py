"""The Metadata Librarian's evaluation: the case file, the run against the committed baseline, and
the category scorers on a draft that suggests categories, which the librarian does not yet do.

No test here carries a requirement marker: the evaluation measures how well the librarian does,
which is not a conformance claim (docs/specs/evaluation.md, invariant 9).
"""

from __future__ import annotations

import asyncio
import gc
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from inspect_ai import eval as inspect_eval
from inspect_ai.log import EvalLog
from inspect_ai.scorer import NOANSWER, Score, Scorer, Target
from inspect_ai.solver import TaskState

from dd_agent_advisor_metadata.evals import drafting
from dd_agent_advisor_metadata.evals.drafting import load_cases, metadata_drafting
from dd_agent_advisor_metadata.evals.scorers import subjects_recalled, terms_cited
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.models import DraftRequest
from workbench.evaluation import baseline_of, differences

# Inspect AI leaves its sample-event stream unclosed (inspect_ai/hooks/_hooks.py); with warnings as
# errors, its deallocator warning fails whichever test is running when it is collected. As in the
# other agents' evaluation tests, the filter is scoped to this module and
# `collect_inspect_streams` makes sure the collection happens here.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Unclosed <MemoryObjectReceiveStream:ResourceWarning"
)

BASELINE = Path(drafting.__file__).parent / "baseline.json"


@pytest.fixture(autouse=True)
def collect_inspect_streams() -> Iterator[None]:
    yield
    gc.collect()


@pytest.fixture
def principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The evaluation acts for whoever runs it (docs/specs/policy-and-identity.md); here, the test
    principal. The librarian's own configuration is cleared, so the template suggester is used."""
    for variable in drafting.CONFIG_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)


def run(tmp_path: Path) -> EvalLog:
    [log] = inspect_eval(metadata_drafting(), model="none", log_dir=str(tmp_path), display="none")
    assert log.status == "success", log.error
    return log


def test_the_case_file_has_unique_ids_and_valid_inputs() -> None:
    cases = load_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    for case in cases:
        DraftRequest.model_validate(case["input"])
        expect = case["expect"]
        if expect["status"] == "succeeded":
            # Every drafted case names the categories a curator would choose.
            assert expect["subjects"], case["id"]
        else:
            assert "reason_code" in expect, case["id"]


def test_no_case_scores_below_the_committed_baseline(tmp_path: Path, principal: None) -> None:
    """The regression gate. A case that improves shows as a change; record it by rewriting the
    baseline (`workbench/scripts/eval_compare.py --write-baseline`) in a commit of its own."""
    log = run(tmp_path)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = baseline_of(log)
    regressions, changes = differences(baseline["scores"], current["scores"])
    assert regressions == []
    assert changes == [], "scores improved: rewrite baseline.json in its own commit"
    for key in ("cases_sha256", "rule_table_sha256", "system_prompt_sha256", "spec_version"):
        assert current["identity"][key] == baseline["identity"][key], key


# --- The category scorers ---------------------------------------------------------------------

SOIL = "4106 Soil sciences"


def _state(suggested: str | None, evidence: list[dict[str, Any]]) -> TaskState:
    """A finished case whose draft asks for an ANZSRC category, suggesting `suggested`."""
    record = {"subjects": [{"subject": None, "subjectScheme": "ANZSRC Fields of Research"}]}
    question: dict[str, Any] = {"question_id": "q-1", "gap_property": "subjects[0].subject"}
    if suggested is not None:
        question["suggested_answer"] = suggested
    envelope = {
        "outcome": {"status": "succeeded"},
        "payload": {"document_text": json.dumps(record), "document_questions": [question]},
        "evidence": [{"source_id": "input:1", "content": {}}, *evidence],
    }
    expect = {"status": "succeeded", "subjects": {"4106": "Soil sciences", "4105": "Pollution"}}
    return cast(TaskState, SimpleNamespace(metadata={"envelope": envelope, "expect": expect}))


def _score(made: Scorer, state: TaskState) -> Score:
    score = asyncio.run(made(state, Target("succeeded")))
    assert isinstance(score, Score)
    return score


def test_a_suggested_category_that_a_retrieved_record_gives_is_recalled_and_cited() -> None:
    record = {"source_id": "tool:subjects/anzsrc-for:4106", "content": {"label": SOIL}}
    state = _state(SOIL, [record])
    recalled = _score(subjects_recalled(), state)
    assert recalled.value == 0.5 and recalled.metadata == {"missing": ["4105"]}
    assert _score(terms_cited(), state).value == 1.0


def test_a_category_no_retrieved_record_gives_is_uncited() -> None:
    state = _state(SOIL, [])
    assert _score(subjects_recalled(), state).value == 0.5
    cited = _score(terms_cited(), state)
    assert cited.value == 0.0 and cited.metadata == {"uncited": [SOIL]}


def test_a_draft_that_suggests_no_category_recalls_none_and_cites_nothing() -> None:
    state = _state(None, [])
    assert _score(subjects_recalled(), state).value == 0.0
    assert _score(terms_cited(), state).value == NOANSWER

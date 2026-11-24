"""The Metadata Librarian's evaluation: the case file, the run against the committed baseline, the
whole evaluation with a fake model choosing categories through the tool gateway, and the category
scorers on hand-made drafts.

No test here carries a requirement marker: the evaluation measures how well the librarian does,
which is not a conformance claim (docs/specs/evaluation.md, invariant 9).
"""

from __future__ import annotations

import asyncio
import gc
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from inspect_ai import eval as inspect_eval
from inspect_ai.log import EvalLog
from inspect_ai.scorer import CORRECT, NOANSWER, Score, Scorer, Target
from inspect_ai.solver import TaskState

from dd_agent_advisor_metadata.agent import MetadataLibrarian
from dd_agent_advisor_metadata.evals import drafting
from dd_agent_advisor_metadata.evals.drafting import load_cases, metadata_drafting
from dd_agent_advisor_metadata.evals.scorers import subjects_recalled, terms_cited
from dd_agent_advisor_metadata.suggest import ModelSuggester
from dd_agent_advisor_metadata.testing import asked_in, facts_in, suggestion_reply
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.models import DraftRequest
from dd_sdk.model import ModelRequest
from dd_sdk.testing import FakeModel
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


def scores(log: EvalLog, case: str) -> dict[str, Score]:
    [sample] = [s for s in log.samples or [] if s.id == case]
    return dict(sample.scores or {})


def test_the_case_file_has_unique_ids_and_valid_inputs() -> None:
    cases = load_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    for case in cases:
        DraftRequest.model_validate(case["input"])
        expect = case["expect"]
        fields = case["input"].get("requirements", {}).get("fields", [])
        if expect["status"] == "succeeded" and any(f.get("qualifier") for f in fields):
            # Every drafted case whose repository asks for categories names those a curator
            # would choose.
            assert expect["subjects"], case["id"]
        elif expect["status"] != "succeeded":
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
    keys = ("cases_sha256", "definitions_sha256", "shares_sha256", "system_prompt_sha256")
    for key in (*keys, "spec_version"):
        assert current["identity"][key] == baseline["identity"][key], key


# --- With a model, through the tool gateway ---------------------------------------------------

type Pick = Callable[[dict[str, str]], str]


def _files(case: dict[str, Any]) -> tuple[str, ...]:
    return tuple(f["file_path"] for f in case["input"]["inventory"]["inventory_files"])


def curator(pick: Pick) -> Callable[[ModelRequest], str]:
    """A model that answers each category question offered with `pick` of the categories the
    case's curator chose, telling the case by its files. It suggests nothing else."""
    wanted = {_files(c): c["expect"].get("subjects") or {} for c in load_cases()}

    def reply(sent: ModelRequest) -> str:
        files = tuple(f["path"] for f in facts_in(sent)["files"])
        chosen = {str(k): v for k, v in wanted[files].items()}
        return suggestion_reply(
            {q["question_id"]: pick(chosen) for q in asked_in(sent) if q.get("choose_from")}
        )

    return reply


def with_model(monkeypatch: pytest.MonkeyPatch, model: FakeModel) -> None:
    monkeypatch.setattr(
        drafting, "librarian", lambda: MetadataLibrarian(suggester=ModelSuggester(model))
    )


def drafted_with_categories() -> list[dict[str, Any]]:
    return [c for c in load_cases() if c["expect"].get("subjects")]


def test_with_a_model_each_category_is_a_curators_choice_and_cites_its_record(
    tmp_path: Path, principal: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model is offered the classification's fields, retrieved through the gateway the
    evaluation's conductor serves, and answers with the first category the curator chose. Each
    suggestion is then recalled and cited by the record the gateway returned."""
    model = FakeModel(curator(lambda chosen: next(iter(chosen))), hosting="local")
    with_model(monkeypatch, model)
    log = run(tmp_path)
    assert any(q.get("choose_from") for sent in model.sent for q in asked_in(sent))
    for case in drafted_with_categories():
        got = scores(log, case["id"])
        first = next(iter(case["expect"]["subjects"]))
        assert got["grounding_passed"].value == CORRECT, case["id"]
        assert got["subjects_recalled"].as_float() > 0, case["id"]
        assert first not in (got["subjects_recalled"].metadata or {}).get("missing", []), case
        assert got["terms_cited"].value == 1.0, case["id"]


def test_with_a_model_a_category_outside_the_classification_is_not_offered(
    tmp_path: Path, principal: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A code the classification does not hold is dropped before the gateway is asked for its
    record, so nothing uncited reaches the researcher and nothing is recalled."""
    with_model(monkeypatch, FakeModel(curator(lambda _chosen: "9999"), hosting="local"))
    log = run(tmp_path)
    for case in drafted_with_categories():
        got = scores(log, case["id"])
        assert got["subjects_recalled"].value == 0.0, case["id"]
        assert got["terms_cited"].value == NOANSWER, case["id"]
        assert got["grounding_passed"].value == CORRECT, case["id"]


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
        "payload": {
            "conforms_to": "http://datacite.org/schema/kernel-4",
            "media_type": "application/json",
            "document_text": json.dumps(record),
            "document_questions": [question],
        },
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

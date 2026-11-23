"""The Data Management Planner's evaluation: the case file, the run against the baseline on
the template path, and the read scorers, which apply only when a model reads a plan.

No test here carries a requirement marker: the evaluation measures how well the checker does,
which is not a conformance claim (docs/specs/evaluation.md, invariant 9).
"""

from __future__ import annotations

import gc
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import yaml
from inspect_ai import eval as inspect_eval
from inspect_ai.log import EvalLog
from inspect_ai.scorer import Score

from dd_agent_advisor_dmp.agent import DmpChecker
from dd_agent_advisor_dmp.classes import DmpCommitments
from dd_agent_advisor_dmp.evals import reading
from dd_agent_advisor_dmp.evals.reading import dmp_reading, load_cases
from dd_agent_advisor_dmp.match import ModelMatcher
from dd_agent_advisor_dmp.read_plan import READ_PROMPT, ModelReader, normalise
from dd_harness.testing import TEST_PRINCIPAL
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

BASELINE = Path(reading.__file__).parent / "baseline.json"
SPEC = yaml.safe_load(reading.CASES.read_text(encoding="utf-8"))
NO_MATCH = json.dumps({"pairings": [], "equivalences": []})
AUDIO = "The audio recordings will not be shared"


@pytest.fixture(autouse=True)
def collect_inspect_streams() -> Iterator[None]:
    yield
    gc.collect()


@pytest.fixture
def principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The evaluation acts for whoever runs it (docs/specs/policy-and-identity.md); here, the test
    principal. The checker's own configuration is cleared, so the template path is evaluated."""
    for variable in reading.CONFIG_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)


def run(tmp_path: Path) -> EvalLog:
    [log] = inspect_eval(dmp_reading(), model="none", log_dir=str(tmp_path), display="none")
    assert log.status == "success", log.error
    return log


def scores(log: EvalLog, case: str) -> dict[str, Score]:
    [sample] = [s for s in log.samples or [] if s.id == case]
    return dict(sample.scores or {})


def test_the_case_file_has_unique_ids_and_valid_inputs() -> None:
    cases = load_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    assert {c["kind"] for c in cases} == {"read", "compare"}
    for case in cases:
        DmpCommitments.model_validate(case["input"])


def test_a_complete_a_partial_and_a_vague_plan_are_read() -> None:
    read = {c["plan"] for c in load_cases() if c["kind"] == "read"}
    assert read == {"complete", "partial", "vague"}
    assert SPEC["plans"]["vague"]["vague"] is True
    assert SPEC["plans"]["vague"]["commitments"] == []


@pytest.mark.parametrize("plan", sorted(SPEC["plans"]))
def test_every_labelled_quote_is_in_its_plan(plan: str) -> None:
    text = normalise((reading.DATA / SPEC["plans"][plan]["file"]).read_text(encoding="utf-8"))
    for label in SPEC["plans"][plan]["commitments"]:
        assert normalise(label["quote"]) in text, label["output"]


def test_on_the_template_path_a_plan_is_not_read_and_a_correction_is_compared() -> None:
    cases = {c["id"]: c for c in load_cases(reads=False)}
    assert cases["read-complete"]["expect"]["status"] == "abstained"
    assert {c["expect"]["status"] for c in load_cases(reads=True)} == {"succeeded"}
    # What the researcher corrected is what the checker is given as confirmed.
    [scripts] = [
        f
        for f in cases["compare-partial"]["input"]["project_decisions"]
        if f["fact_subject"] == "Analysis scripts"
    ]
    assert scripts["commitment_repository"] == "GitHub"


def test_no_case_scores_below_the_committed_baseline(tmp_path: Path, principal: None) -> None:
    """The regression gate, on the template path. A case that improves shows as a change; record
    it by rewriting the baseline (`workbench/scripts/eval_compare.py --write-baseline`) in a
    commit of its own."""
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = baseline_of(run(tmp_path))
    regressions, changes = differences(baseline["scores"], current["scores"])
    assert regressions == []
    assert changes == [], "scores improved: rewrite baseline.json in its own commit"
    for key in ("cases_sha256", "read_prompt_sha256", "data_sha256", "spec_version"):
        assert current["identity"][key] == baseline["identity"][key], key


# --- With a model -----------------------------------------------------------------------------


def labelled_reply(extra: dict[str, list[dict[str, object]]]) -> Callable[[ModelRequest], str]:
    """A fake model that reads each plan exactly as labelled, adds what `extra` gives for it, and
    reconciles nothing when matching."""

    def reply(request: ModelRequest) -> str:
        if request.system != READ_PROMPT:
            return NO_MATCH
        content = str(request.messages[0]["content"])  # type: ignore[index]
        text = json.loads(content.split("\n", 1)[1])[0]["text"]
        name, plan = next(
            (n, p)
            for n, p in SPEC["plans"].items()
            if (reading.DATA / p["file"]).read_text(encoding="utf-8") == text
        )
        read = [
            {
                "document": 1,
                **{k: label[k] for k in ("output", "repository", "access", "licence")},
                "quote": " ".join(label["quote"].split()),
            }
            for label in plan["commitments"]
        ]
        read += extra.get(name, [])
        return json.dumps({"commitments": read, "vague": plan.get("vague", False)})

    return reply


def with_model(monkeypatch: pytest.MonkeyPatch, model: FakeModel) -> None:
    monkeypatch.setattr(
        reading, "checker", lambda: DmpChecker(ModelMatcher(model), ModelReader(model))
    )


def test_with_a_model_the_reading_scorers_apply(
    tmp_path: Path, principal: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeModel(labelled_reply({}), hosting="local")
    with_model(monkeypatch, model)
    log = run(tmp_path)
    assert model.sent, "the fake model was called"

    for case in ("read-complete", "read-partial"):
        got = scores(log, case)
        assert got["outcome_matches"].value == "C"
        assert got["outputs_recalled"].value == 1.0
        assert got["aspects_agree"].value == 1.0
        assert got["no_unlabelled_commitment"].value == "C"
        assert got["quotes_found"].value == "C"
    vague = scores(log, "read-vague")
    assert vague["outcome_matches"].value == "C"
    assert vague["no_unlabelled_commitment"].value == "C"
    assert vague["outputs_recalled"].value == "N"  # nothing is labelled to recall
    assert scores(log, "compare-partial")["discrepancies_match"].value == "C"


def test_the_evaluation_catches_a_commitment_the_plan_does_not_make(
    tmp_path: Path, principal: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A model that reads the audio recordings, which the partial plan says will not be shared,
    as a commitment is caught; one whose quote the plan does not hold is dropped by the checker,
    so its quote never reaches the researcher."""
    extra = {
        "partial": [read_as("Audio recordings", AUDIO)],
        "complete": [
            read_as("Field notebooks", "Field notebooks will be scanned and deposited in the EIDC.")
        ],
    }
    with_model(monkeypatch, FakeModel(labelled_reply(extra), hosting="local"))
    log = run(tmp_path)

    partial = scores(log, "read-partial")
    assert partial["no_unlabelled_commitment"].value == "I"
    assert "Audio recordings" in (partial["no_unlabelled_commitment"].metadata or {})["unlabelled"]
    assert partial["quotes_found"].value == "C"
    complete = scores(log, "read-complete")
    assert complete["no_unlabelled_commitment"].value == "C"
    assert complete["quotes_found"].value == "C"


def read_as(output: str, quote: str) -> dict[str, object]:
    found = {"repository": None, "access": None, "licence": None}
    return {"document": 1, "output": output, "quote": quote, **found}

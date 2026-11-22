"""The Rights and Licensing Adviser's evaluation: the case file, the run against the committed
baseline, and the free-word cases read by a fake model.

No test here carries a requirement marker: the evaluation measures how well the adviser does,
which is not a conformance claim (docs/specs/evaluation.md, invariant 9).
"""

from __future__ import annotations

import gc
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from inspect_ai import eval as inspect_eval
from inspect_ai.log import EvalLog
from inspect_ai.scorer import Score

from dd_agent_advisor_rights.agent import RightsAdviser
from dd_agent_advisor_rights.classes import RightsContext
from dd_agent_advisor_rights.evals import choosing
from dd_agent_advisor_rights.evals.choosing import load_cases, rights_choosing
from dd_agent_advisor_rights.evals.scorers import QUESTIONS
from dd_agent_advisor_rights.interpret import ModelInterpreter
from dd_agent_advisor_rights.testing import rights_reply
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

BASELINE = Path(choosing.__file__).parent / "baseline.json"
FREE_WORDS = ("words-not-to-sell", "words-keep-it-open", "words-public-domain", "words-credit-us")


@pytest.fixture(autouse=True)
def collect_inspect_streams() -> Iterator[None]:
    yield
    gc.collect()


@pytest.fixture
def principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The evaluation acts for whoever runs it (docs/specs/policy-and-identity.md); here, the test
    principal. The adviser's own configuration is cleared, so the template interpreter is used."""
    for variable in choosing.CONFIG_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)


def run(tmp_path: Path) -> EvalLog:
    [log] = inspect_eval(rights_choosing(), model="none", log_dir=str(tmp_path), display="none")
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
        RightsContext.model_validate(case["input"])
        assert set(case["expect"].get("questions", [])) <= set(QUESTIONS)
        overlap = set(case["expect"].get("include", [])) & set(case["expect"].get("exclude", []))
        assert not overlap, case["id"]


def test_every_case_expects_a_stop_or_something_to_score() -> None:
    """A case that answers names what a steward expects of the answer: false negatives are only
    measured where the case says what must not be missed."""
    for case in load_cases():
        expect = case["expect"]
        if expect["status"] == "succeeded":
            assert {"include", "access_first", "questions"} & set(expect), case["id"]


def test_no_case_scores_below_the_committed_baseline(tmp_path: Path, principal: None) -> None:
    """The regression gate. A case that improves shows as a change; record it by rewriting the
    baseline (`workbench/scripts/eval_compare.py --write-baseline`) in a commit of its own."""
    log = run(tmp_path)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = baseline_of(log)
    regressions, changes = differences(baseline["scores"], current["scores"])
    assert regressions == []
    assert changes == [], "scores improved: rewrite baseline.json in its own commit"
    for key in ("cases_sha256", "licences_sha256", "system_prompt_sha256", "spec_version"):
        assert current["identity"][key] == baseline["identity"][key], key


# --- With a model -----------------------------------------------------------------------------

NOT_TO_SELL = "Anyone may use it, but nobody may sell it."

# How a data steward reads each free-word wish: the reuse values and licences that fit it.
READINGS = {
    NOT_TO_SELL: (["non-commercial"], ["CC-BY-NC-4.0"]),
    "Whatever people build from it must be shared on the same terms.": (
        ["share-alike"],
        ["ODbL-1.0"],
    ),
    "Public domain, no strings attached.": (["any"], ["CC0-1.0"]),
    "Fine to reuse for anything, as long as we are credited.": (
        ["attribution"],
        ["CC-BY-4.0", "ODC-By-1.0"],
    ),
}


def steward_reply(
    misread: dict[str, tuple[list[str], list[str]]] | None = None,
) -> Callable[[ModelRequest], str]:
    """A fake model that reads each wish as `READINGS` does, except those it `misread`s."""
    readings = {**READINGS, **(misread or {})}

    def reply(request: ModelRequest) -> str:
        content = str(request.messages[0]["content"])  # type: ignore[index]
        said = json.loads(content.split("\n", 1)[1])["said"].get("reuse_wanted")
        reuse, licences = readings.get(said, ([], []))
        return rights_reply(reuse, licences)

    return reply


def with_model(monkeypatch: pytest.MonkeyPatch, model: FakeModel) -> None:
    monkeypatch.setattr(
        choosing, "adviser", lambda: RightsAdviser(interpreter=ModelInterpreter(model))
    )


def test_with_a_model_the_free_word_wishes_offer_what_fits(
    tmp_path: Path, principal: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeModel(steward_reply(), hosting="local")
    with_model(monkeypatch, model)
    log = run(tmp_path)
    assert model.sent, "the fake model was called"
    for case in FREE_WORDS:
        got = scores(log, case)
        assert got["ids_recalled"].value == 1.0, case
        assert got["none_listed"].value == 1.0, case


def test_the_evaluation_catches_a_misread_wish(
    tmp_path: Path, principal: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A model that reads "nobody may sell it" as any reuse offers licences that allow selling.
    The closed-set check cannot catch that, since they fit the reading; the evaluation does, as
    wrong licences scored apart from recall."""
    misread = {NOT_TO_SELL: (["any"], ["CC0-1.0", "CC-BY-4.0"])}
    with_model(monkeypatch, FakeModel(steward_reply(misread), hosting="local"))
    log = run(tmp_path)
    not_to_sell = scores(log, "words-not-to-sell")
    assert not_to_sell["ids_recalled"].value == 0.0
    assert not_to_sell["none_listed"].value == 0.0
    assert {"CC0-1.0", "CC-BY-4.0"} <= set((not_to_sell["none_listed"].metadata or {})["wrong"])

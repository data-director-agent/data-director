"""The Documentation Editor's evaluation: the defects, the case file, the run against the baseline
on the template path, and the scorers that apply only when a model writes prose or suggests
answers.

No test here carries a requirement marker: the evaluation measures how well the editor does, which
is not a conformance claim (docs/specs/evaluation.md, invariant 9).
"""

from __future__ import annotations

import copy
import gc
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from inspect_ai import eval as inspect_eval
from inspect_ai.log import EvalLog
from inspect_ai.scorer import NOANSWER, Score

from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_documentation.evals import drafting
from dd_agent_advisor_documentation.evals.defects import DEFECTS, apply_defect
from dd_agent_advisor_documentation.evals.drafting import (
    base_request,
    documentation_drafting,
    load_cases,
)
from dd_agent_advisor_documentation.prose import SYSTEM_PROMPT, ModelWriter, ProseReply
from dd_agent_advisor_documentation.suggestions import SUGGEST_PROMPT
from dd_agent_advisor_documentation.testing import prose_reply, suggestion_reply
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.models import DocumentKind, DraftRequest, FileInventory
from dd_sdk.model import ModelRequest
from dd_sdk.testing import FakeModel
from workbench.evaluation import baseline_of, differences

# Inspect AI leaves its sample-event stream unclosed (inspect_ai/hooks/_hooks.py); with warnings as
# errors, its deallocator warning fails whichever test is running when it is collected. As in the
# standards advisor's evaluation tests, the filter is scoped to this module and
# `collect_inspect_streams` makes sure the collection happens here.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Unclosed <MemoryObjectReceiveStream:ResourceWarning"
)

EVALS = Path(drafting.__file__).parent
BASELINE = EVALS / "baseline.json"
SPEC = yaml.safe_load(drafting.CASES.read_text(encoding="utf-8"))
HALLAM = base_request(SPEC["bases"]["hallam-moor"])


@pytest.fixture(autouse=True)
def collect_inspect_streams() -> Iterator[None]:
    yield
    gc.collect()


@pytest.fixture
def principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The evaluation acts for whoever runs it (docs/specs/policy-and-identity.md); here, the test
    principal. The editor's own configuration is cleared, so the template path is evaluated."""
    for variable in drafting.CONFIG_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)


def run(tmp_path: Path) -> EvalLog:
    [log] = inspect_eval(
        documentation_drafting(), model="none", log_dir=str(tmp_path), display="none"
    )
    assert log.status == "success", log.error
    return log


def scores(log: EvalLog, case: str) -> dict[str, Score]:
    [sample] = [s for s in log.samples or [] if s.id == case]
    return dict(sample.scores or {})


@pytest.mark.parametrize("name", sorted(DEFECTS))
def test_a_defect_copies_its_input_and_gives_the_same_result_every_time(name: str) -> None:
    before = copy.deepcopy(HALLAM)
    first = apply_defect(name, HALLAM)
    assert before == HALLAM
    assert apply_defect(name, HALLAM) == first
    DraftRequest.model_validate(first | {"document_kind": DocumentKind.README})


def test_every_defect_but_none_changes_the_base_request() -> None:
    changed = {name for name in DEFECTS if apply_defect(name, HALLAM) != HALLAM}
    assert changed == set(DEFECTS) - {"none"}


def test_the_case_file_names_registered_defects_unique_ids_and_valid_requests() -> None:
    cases = load_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    assert {c["defect"] for c in cases} <= set(DEFECTS)
    for case in cases:
        DraftRequest.model_validate(case["input"])


def test_the_gold_names_fields_the_inventory_has() -> None:
    inventory = FileInventory.model_validate(HALLAM["inventory"])
    names = {c.name for f in inventory.inventory_files for c in f.file_fields}
    assert set(SPEC["gold"]["hallam-moor"]) <= names


def test_no_case_scores_below_the_committed_baseline(tmp_path: Path, principal: None) -> None:
    """The regression gate, on the template path. A case that improves shows as a change; record
    it by rewriting the baseline (`workbench/scripts/eval_compare.py --write-baseline`) in a
    commit of its own."""
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = baseline_of(run(tmp_path))
    regressions, changes = differences(baseline["scores"], current["scores"])
    assert regressions == []
    assert changes == [], "scores improved: rewrite baseline.json in its own commit"
    for key in ("cases_sha256", "readme_template_sha256", "data_sha256", "spec_version"):
        assert current["identity"][key] == baseline["identity"][key], key


# --- With a model -----------------------------------------------------------------------------

# What the fake model suggests, by field name. `SM` is recorded in raw counts, so `%` is the
# confidently wrong suggestion the crib sheet warns of.
UNITS = {"T_air": "°C", "SM": "%", "vwc": "%", "Batt": "volts"}
DEFINITIONS = {"T_air": "Air temperature at the logger node."}


def reply(request: ModelRequest) -> str:
    """A fake model that suggests what `UNITS` and `DEFINITIONS` say, writes for the README an
    overview that names only a count the facts give, and suggests nothing for a README's
    questions."""
    content = str(request.messages[0]["content"])  # type: ignore[index]
    if request.system == SYSTEM_PROMPT:
        facts = json.loads(content.split("Facts:\n", 1)[1])
        return prose_reply({"overview": f"The dataset has {facts['file_count']} files."})
    if request.system != SUGGEST_PROMPT:
        return suggestion_reply({})
    questions = json.loads(
        content.split("Questions you may suggest an answer to:\n", 1)[1].split("\n\nFacts:", 1)[0]
    )
    given = {"unit": UNITS, "description": DEFINITIONS}
    return suggestion_reply(
        {
            q["question_id"]: suggestion
            for q in questions
            if (suggestion := given.get(q["column"], {}).get(q["field"]))
        }
    )


def test_with_a_model_the_suggestions_and_prose_are_scored_and_no_cell_is_written(
    tmp_path: Path, principal: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeModel(reply)
    monkeypatch.setattr(drafting, "editor", lambda: DocumentationEditor(writer=ModelWriter(model)))
    log = run(tmp_path)
    assert model.sent, "the fake model was called"

    dictionary = scores(log, "hallam-dictionary")
    # T_air's unit and definition (in both phase 1 files), vwc's and Batt's units agree with the
    # crib sheet; SM's unit, suggested twice, does not.
    suggested = dictionary["suggestions_match_gold"]
    assert suggested.value == pytest.approx(7 / 9)
    assert all(" SM unit" in p for p in (suggested.metadata or {})["problems"])
    # The model suggested answers, and still no cell holds a value no source accounts for.
    assert dictionary["no_model_value_in_cell"].value == "C"
    assert dictionary["every_cell_sourced"].value == "C"

    readme = scores(log, "hallam-readme")
    assert readme["no_unsupported_claim"].value == "C"
    assert readme["every_gap_marked_and_asked"].value == 1.0

    # The first run asks before it writes: a note, not a README, so its sections are not scored.
    first = scores(log, "hallam-readme-first")
    assert first["every_gap_marked_and_asked"].value == 1.0
    assert first["required_sections_present"].value == NOANSWER


def test_the_evaluation_catches_what_the_editors_own_guards_stop(
    tmp_path: Path, principal: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the editor's guards switched off, the evaluation scores the faults they stop: prose
    naming a count the facts do not give, and a unit written into a cell as if inferred."""
    from dd_agent_advisor_documentation import dictionary, prose

    def keep_everything(reply: ProseReply, facts: object, sections: object) -> prose.Prose:
        kept = {p.section: p.paragraph for p in reply.sections if p.paragraph}
        return prose.Prose(reply.overview, kept)

    def guessed_unit(column: str, given: str, before: object) -> tuple[str, dictionary.Source]:
        if column == "unit":
            return "°C", dictionary.Source.INFERRED
        return cell(column, given, before)  # type: ignore[arg-type]

    cell = dictionary._cell
    monkeypatch.setattr(prose, "check", keep_everything)
    monkeypatch.setattr(dictionary, "_cell", guessed_unit)
    invented = FakeModel(
        lambda r: (
            prose_reply({"overview": "The dataset has 999 files."})
            if r.system == SYSTEM_PROMPT
            else suggestion_reply({})
        )
    )
    monkeypatch.setattr(
        drafting, "editor", lambda: DocumentationEditor(writer=ModelWriter(invented))
    )
    log = run(tmp_path)

    claim = scores(log, "hallam-readme")["no_unsupported_claim"]
    assert claim.value == "I" and "'999'" in (claim.explanation or "")
    assert scores(log, "hallam-dictionary")["no_model_value_in_cell"].value == "I"

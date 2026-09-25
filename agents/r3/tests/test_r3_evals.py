"""R3's seeded-defect evaluation: the defects, the case file, and the run against the baseline.

No test here carries a requirement marker: the evaluation measures how well R3 does, which is
not a conformance claim (ADR-0013).
"""

from __future__ import annotations

import copy
import gc
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from inspect_ai import eval as inspect_eval

from dd_agent_r3.evals.defects import DEFECTS, apply_defect
from dd_agent_r3.evals.seeded import load_cases, r3_seeded
from dd_agent_r3.testing import SAMPLES
from dd_sdk.contract.models import parse_input
from workbench.evaluation import baseline_of, differences

# Inspect AI leaves its sample-event stream unclosed (inspect_ai/hooks/_hooks.py, the sample
# event emitter); with warnings as errors, its deallocator warning fails whichever test is
# running when it is collected. The filter is scoped to this module, so a stream leaked by the
# workbench still fails elsewhere, and `collect_inspect_streams` makes sure the collection
# happens here rather than in a later module.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Unclosed <MemoryObjectReceiveStream:ResourceWarning"
)


@pytest.fixture(autouse=True)
def collect_inspect_streams() -> Iterator[None]:
    yield
    gc.collect()


BASELINE = Path(__file__).resolve().parents[1] / "src" / "dd_agent_r3" / "evals" / "baseline.json"
SOIL = json.loads((SAMPLES / "soil-chemistry.profile.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(DEFECTS))
def test_a_defect_copies_its_input_and_gives_the_same_result_every_time(name):
    before = copy.deepcopy(SOIL)
    first = apply_defect(name, SOIL)
    assert before == SOIL
    assert apply_defect(name, SOIL) == first
    parse_input(first)  # still a valid DatasetProfile


def test_every_defect_but_none_changes_the_base_profile():
    changed = {name for name in DEFECTS if apply_defect(name, SOIL) != SOIL}
    assert changed == set(DEFECTS) - {"none"}


def test_the_case_file_names_registered_defects_and_unique_ids():
    cases = load_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    assert {c["defect"] for c in cases} <= set(DEFECTS)
    assert {c["backend"] for c in cases} <= {"snapshot", "unavailable"}


def test_no_case_scores_below_the_committed_baseline(tmp_path, monkeypatch):
    """The regression gate. A case that improves shows as a change; record it by rewriting the
    baseline (`workbench/scripts/eval_compare.py --write-baseline`) in a commit of its own."""
    for variable in ("DD_R3_RETRIEVAL", "DD_R3_EXPLAINER", "DD_MODEL_ID", "DD_SNAPSHOT_PATH"):
        monkeypatch.delenv(variable, raising=False)
    [log] = inspect_eval(r3_seeded(), model="none", log_dir=str(tmp_path), display="none")
    assert log.status == "success", log.error
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    run = baseline_of(log)
    regressions, changes = differences(baseline["scores"], run["scores"])
    assert regressions == []
    assert changes == [], "scores improved: rewrite baseline.json in its own commit"
    for key in ("ranking_sha256", "snapshot_sha256", "cases_sha256", "spec_version"):
        assert run["identity"][key] == baseline["identity"][key], key

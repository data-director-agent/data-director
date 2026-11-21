"""The repository advisor's evaluation: the case file, and the run against the committed baseline.

No test here carries a requirement marker: the evaluation measures how well the advisor does,
which is not a conformance claim (docs/specs/evaluation.md, invariant 9). The run needs the full
re3data registry (`uv run dd-sources prepare`), which CI builds; without it, it is skipped.
"""

from __future__ import annotations

import gc
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from inspect_ai import eval as inspect_eval

from dd_agent_advisor_repository import registry
from dd_agent_advisor_repository.classes import RepositoryNeeds
from dd_agent_advisor_repository.evals import shortlist
from dd_agent_advisor_repository.evals.shortlist import load_cases, repository_shortlist
from dd_harness.testing import TEST_PRINCIPAL
from workbench.evaluation import baseline_of, differences

# Inspect AI leaves its sample-event stream unclosed (inspect_ai/hooks/_hooks.py); with warnings as
# errors, its deallocator warning fails whichever test is running when it is collected. As in the
# other agents' evaluation tests, the filter is scoped to this module and
# `collect_inspect_streams` makes sure the collection happens here.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Unclosed <MemoryObjectReceiveStream:ResourceWarning"
)

BASELINE = Path(shortlist.__file__).parent / "baseline.json"
PROBLEM = registry.problem()


@pytest.fixture(autouse=True)
def collect_inspect_streams() -> Iterator[None]:
    yield
    gc.collect()


@pytest.fixture
def principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The evaluation acts for whoever runs it (docs/specs/policy-and-identity.md); here, the test
    principal. The advisor's own configuration is cleared, so the template explainer is used."""
    for variable in shortlist.CONFIG_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)


def test_the_case_file_has_unique_ids_and_valid_inputs() -> None:
    cases = load_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    for case in cases:
        RepositoryNeeds.model_validate(case["input"])


def test_both_ways_of_reading_the_plan_name_the_same_repositories() -> None:
    """One commitment per destination, or both in one, the plan names the same repositories."""
    named = {
        c["id"]: c["expect"].get("in_plan") for c in load_cases() if c["input"]["project_decisions"]
    }
    assert len(set(map(tuple, named.values()))) == 1


@pytest.mark.re3data
@pytest.mark.skipif(PROBLEM is not None, reason=f"no full re3data registry: {PROBLEM}")
def test_no_case_scores_below_the_committed_baseline(tmp_path: Path, principal: None) -> None:
    """The regression gate. A case that improves shows as a change; record it by rewriting the
    baseline (`workbench/scripts/eval_compare.py --write-baseline`) in a commit of its own."""
    [log] = inspect_eval(
        repository_shortlist(), model="none", log_dir=str(tmp_path), display="none"
    )
    assert log.status == "success", log.error
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = baseline_of(log)
    regressions, changes = differences(baseline["scores"], current["scores"])
    assert regressions == []
    assert changes == [], "scores improved: rewrite baseline.json in its own commit"
    for key in ("cases_sha256", "ranking_sha256", "aliases_sha256", "spec_version"):
        assert current["identity"][key] == baseline["identity"][key], key

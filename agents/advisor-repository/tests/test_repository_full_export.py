"""Shortlists over the whole pinned re3data export, where a broad theme finds more repositories
of the discipline than the cap and the committed fixture cannot show it (#1169).

Skipped unless the registry has been built: `uv run dd-re3data fetch`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dd_agent_advisor_repository import rank, registry
from dd_agent_advisor_repository.agent import RepositoryAgent
from dd_agent_advisor_repository.classes import RepositoryNeeds, RepositoryOptions
from dd_agent_advisor_repository.snapshot import FairsharingSnapshot, Re3dataRegistry
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import OutcomeStatus

PROBLEM = registry.problem()

pytestmark = [
    pytest.mark.re3data,
    pytest.mark.skipif(PROBLEM is not None, reason=f"no full re3data registry: {PROBLEM}"),
]

NEEDS = Path(__file__).parent / "data" / "needs"
ZENODO = "r3d100010468"


def shortlist(runs_dir: Path, needs: RepositoryNeeds) -> RepositoryOptions:
    conductor = make_conductor(runs_dir, RepositoryAgent(Re3dataRegistry(), FairsharingSnapshot()))
    env = conductor.invoke(request("advisor.repository", needs), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    return env.payload_as(RepositoryOptions)


def dataset_b() -> RepositoryNeeds:
    """Workshop Dataset B: perovskite XRD and SEM."""
    raw = json.loads((NEEDS / "perovskite-xrd-sem.json").read_text(encoding="utf-8"))
    return RepositoryNeeds.model_validate(raw)


@pytest.mark.parametrize(
    "themes",
    [None, ["materials science"]],
    ids=["as-given", "one-broad-theme"],
)
def test_dataset_b_is_offered_zenodo_as_its_generalist(
    tmp_path: Path, themes: list[str] | None
) -> None:
    needs = dataset_b() if themes is None else dataset_b().model_copy(update={"themes": themes})
    options = shortlist(tmp_path, needs)
    ids = [c.grounded_on[0].source_id for c in options.candidates]
    assert len(ids) == rank.config()["max_candidates"]
    assert set(ids) & set(rank.generalists()), ids
    assert ZENODO in ids, ids
    zenodo = options.candidates[ids.index(ZENODO)]
    assert zenodo.ranked_by[0].startswith("A generalist repository")

"""fact.checker through the conductor: a retrieval-mode agent that is not R3-shaped."""

from __future__ import annotations

from pathlib import Path

import pytest

import dd_agent_factcheck
from dd_agent_factcheck.agent import FactChecker, InMemorySources, Source
from dd_agent_factcheck.classes import Claim, FactCheck, Verdict
from dd_sdk.contract.models import (
    GroundingMode,
    OutcomeStatus,
    ReasonCode,
)
from dd_sdk.evidence import DOCUMENT_CANONICALISATION
from dd_sdk.schema import gen
from workbench.testing import TEST_PRINCIPAL, make_conductor, request

SOURCES = InMemorySources(
    [
        Source(
            "s:doi",
            "DOI",
            "A DOI is a persistent identifier. A DOI does not change when the object moves.",
        ),
        Source("s:csv", "CSV", "CSV is a plain text tabular format registered as text/csv."),
    ]
)


def run(runs_dir: Path, text: str, checker: FactChecker | None = None):
    conductor = make_conductor(runs_dir, checker or FactChecker(SOURCES))
    env = conductor.invoke(request("fact.checker", Claim(text=text)), acting_for=TEST_PRINCIPAL)
    return conductor, env


@pytest.mark.requirement("DD-GROUNDING", "DD-GROUNDED-PAYLOAD", "C14.1")
def test_verdict_rests_only_on_retrieved_sources_and_passes_the_linter(runs_dir: Path) -> None:
    conductor, env = run(runs_dir, "A DOI does not change when the object moves.")
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.RETRIEVAL
    payload = env.payload_as(FactCheck)
    assert payload.verdict == Verdict.SUPPORTED  # same negation in claim and source
    assert {g.source_id for g in payload.grounded_on} == {"s:doi"}
    assert [(e.source_id, e.canonicalisation) for e in env.evidence] == [
        ("s:doi", DOCUMENT_CANONICALISATION)
    ]
    report = conductor.grounding_reports[env.invocation_id]
    assert report.passed and report.retrieval_count == 1 and report.chat_count == 0
    assert payload.rationale  # C14


def test_negation_mismatch_refutes(runs_dir: Path) -> None:
    _, env = run(runs_dir, "A DOI does change when the object moves.")
    payload = env.payload_as(FactCheck)
    assert payload.verdict == Verdict.REFUTED


def test_uncovered_claim_is_unverifiable_against_consulted_sources(runs_dir: Path) -> None:
    _, env = run(runs_dir, "A DOI is a persistent tabular format.")
    payload = env.payload_as(FactCheck)
    assert payload.verdict == Verdict.UNVERIFIABLE
    assert {g.source_id for g in payload.grounded_on} == {"s:doi", "s:csv"}


@pytest.mark.requirement("DD-OUTCOME")
def test_abstains_when_nothing_is_retrieved_or_the_claim_is_too_short(runs_dir: Path) -> None:
    _, env = run(runs_dir, "Mediaeval palaeography flourished.")
    assert (env.outcome.status, env.outcome.reason_code) == (
        OutcomeStatus.ABSTAINED,
        ReasonCode.NO_CANDIDATES_RETRIEVED,
    )
    _, env = run(runs_dir / "b", "DOI.")
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


def test_packaged_sources_load_and_the_sample_claim_is_supported(runs_dir: Path) -> None:
    _, env = run(runs_dir, "A DOI does not change when the object moves.", FactChecker())
    payload = env.payload_as(FactCheck)
    assert payload.verdict == Verdict.SUPPORTED


def test_its_classes_are_generated_from_its_own_linkml() -> None:
    source = Path(dd_agent_factcheck.__file__).parent / "schema" / "factcheck.yaml"
    assert gen.stale(source) == [], f"run `uv run dd-gen-schema {source}`"

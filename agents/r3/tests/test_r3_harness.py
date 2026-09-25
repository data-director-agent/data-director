"""R3 through the conductor, with fakes, served in memory over A2A as the workbench calls it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dd_agent_r3 import testing as fakes
from dd_agent_r3.agent import R3Agent
from dd_sdk.contract.models import (
    DatasetProfile,
    InvocationRequest,
    OutcomeStatus,
    ReasonCode,
    RecommendationKind,
    Recommendations,
    TableField,
)
from dd_sdk.tracing import records_from_jsonl
from workbench import grounding

SAMPLES = fakes.SAMPLES
soil_profile = fakes.soil_profile
make_conductor = fakes.make_conductor
request = fakes.request


# --- R3 with fakes ----------------------------------------------------------------------------


@pytest.mark.requirement("R3", "R3.1", "R3.2", "R3.3", "R3.4", "C14")
def test_r3_recommends_across_kinds_with_evidence(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, crate=False)
    env = conductor.invoke(request("r3.standards-advisor"))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.payload is not None
    kinds = {i.kind for i in env.payload.items}
    assert RecommendationKind.CONTROLLED_VOCABULARY in kinds  # AGROVOC (R3.1)
    assert RecommendationKind.ONTOLOGY in kinds  # ENVO (R3.2)
    assert RecommendationKind.DATA_FORMAT in kinds  # CSV (R3.3)
    field_targets = {
        i.target for i in env.payload.items if i.kind == RecommendationKind.FIELD_FORMAT
    }
    assert field_targets == {
        "field:collection_date",
        "field:sampled_at",
        "field:survey_date_uk",
    }  # R3.4
    assert all(i.rationale for i in env.payload.items)  # C14
    cited = {i.resource.fairsharing_id for i in env.payload.items}
    assert {e.source_id for e in env.evidence} == cited
    evidenced = {(e.source_id, e.content_hash) for e in env.evidence}
    for item in env.payload.items:
        assert {(g.source_id, g.content_hash) for g in item.grounded_on} <= evidenced
        # The linter reads only grounded_on; that it names the resource shown is R3's obligation.
        assert [g.source_id for g in item.grounded_on] == [item.resource.fairsharing_id]
    assert {(g.source_id, g.content_hash) for g in env.payload.grounded_on} == evidenced
    assert env.payload.searched is not None and env.payload.searched.candidates_retrieved
    assert conductor.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("R3.5")
def test_deprecated_records_are_never_recommended_and_no_list_is_hard_coded(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, crate=False).invoke(request("r3.standards-advisor"))
    assert env.payload is not None
    assert "FAIRsharing.test-old" not in {i.resource.fairsharing_id for i in env.payload.items}
    # Emerging: an in_development record is kept and flagged.
    emerging = fakes.AGROVOC.model_copy(
        update={"status": "in_development", "fairsharing_id": "FAIRsharing.test-new"}
    )
    r3 = R3Agent(retrieval=fakes.FakeRetrieval([emerging, fakes.CSV]))
    env2 = make_conductor(runs_dir / "b", r3=r3, crate=False).invoke(
        request("r3.standards-advisor")
    )
    assert env2.payload is not None
    assert any(i.resource.status == "in_development" for i in env2.payload.items)


@pytest.mark.requirement("R3.6", "DD-OUTCOME")
def test_r3_abstention_reasons_are_distinct(runs_dir: Path) -> None:
    empty = DatasetProfile.model_validate(json.loads((SAMPLES / "empty.profile.json").read_text()))
    env = make_conductor(runs_dir, crate=False).invoke(request("r3.standards-advisor", empty))
    assert (env.outcome.status, env.outcome.reason_code) == (
        OutcomeStatus.ABSTAINED,
        ReasonCode.INSUFFICIENT_INPUT,
    )

    down = R3Agent(retrieval=fakes.FakeRetrieval(unavailable=True))
    env = make_conductor(runs_dir / "b", r3=down, crate=False).invoke(
        request("r3.standards-advisor")
    )
    assert env.outcome.reason_code == ReasonCode.REGISTRY_UNAVAILABLE

    nothing = R3Agent(retrieval=fakes.FakeRetrieval([]))
    env = make_conductor(runs_dir / "c", r3=nothing, crate=False).invoke(
        request("r3.standards-advisor")
    )
    assert env.outcome.reason_code == ReasonCode.NO_CANDIDATES_RETRIEVED

    unrelated = DatasetProfile(
        title="Mediaeval manuscripts", keywords=["palaeography"], themes=["History"]
    )
    env = make_conductor(runs_dir / "d", crate=False).invoke(
        request("r3.standards-advisor", unrelated)
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code in (
        ReasonCode.NO_QUALIFYING_RESOURCE,
        ReasonCode.NO_CANDIDATES_RETRIEVED,
    )
    assert "Searched" in env.outcome.statement or "returned nothing" in env.outcome.statement


# --- Grounding --------------------------------------------------------------------------------


@pytest.mark.requirement("DD-GROUNDING", "C13.1", "R10")
def test_model_call_after_retrieval_passes_linter_and_records_tokens(runs_dir: Path) -> None:
    r3 = R3Agent(retrieval=fakes.FakeRetrieval(), explainer=fakes.FakeModelExplainer())
    conductor = make_conductor(runs_dir, r3=r3, crate=False)
    env = conductor.invoke(request("r3.standards-advisor"))
    report = conductor.grounding_reports[env.invocation_id]
    assert report.passed and report.chat_count == 1 and report.retrieval_count >= 3
    assert env.telemetry.model_id == "fake-model"
    assert (env.telemetry.input_tokens, env.telemetry.output_tokens) == (100, 50)
    assert env.telemetry.trace_id and len(env.telemetry.trace_id) == 32


@pytest.mark.requirement("DD-GROUNDING")
def test_ungrounded_identifier_in_output_is_withheld(runs_dir: Path) -> None:
    """A recommendation naming something never retrieved must not leave the system."""

    class Smuggler(R3Agent):
        def run(self, req: InvocationRequest, ctx):
            result = super().run(req, ctx)
            assert isinstance(result.payload, Recommendations)
            first = result.payload.items[0]
            item = first.model_copy(
                update={
                    "resource": first.resource.model_copy(
                        update={"fairsharing_id": "FAIRsharing.smuggled"}
                    ),
                    "grounded_on": [
                        first.grounded_on[0].model_copy(
                            update={"source_id": "FAIRsharing.smuggled"}
                        )
                    ],
                }
            )
            payload = result.payload.model_copy(update={"items": [item, *result.payload.items[1:]]})
            return type(result)(outcome=result.outcome, payload=payload, evidence=result.evidence)

    conductor = make_conductor(runs_dir, r3=Smuggler(retrieval=fakes.FakeRetrieval()), crate=False)
    env = conductor.invoke(request("r3.standards-advisor"))
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith("/grounding-violation")
    assert env.payload is None
    assert any(
        v.startswith("G2") for v in conductor.grounding_reports[env.invocation_id].violations
    )


@pytest.mark.requirement("DD-GROUNDING")
def test_chat_before_retrieval_fails_g1(runs_dir: Path) -> None:
    class EagerAgent(R3Agent):
        def run(self, req: InvocationRequest, ctx):
            # A model call before anything was retrieved.
            assert isinstance(req.input, DatasetProfile)
            fakes.FakeModelExplainer().explain(req.input, [], ctx)
            return super().run(req, ctx)

    conductor = make_conductor(
        runs_dir, r3=EagerAgent(retrieval=fakes.FakeRetrieval()), crate=False
    )
    env = conductor.invoke(request("r3.standards-advisor"))
    report = conductor.grounding_reports[env.invocation_id]
    assert not report.passed and any(v.startswith("G1") for v in report.violations)
    assert env.outcome.status == OutcomeStatus.FAILED


def test_linter_runs_offline_over_written_spans(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, crate=False)
    env = conductor.invoke(request("r3.standards-advisor"))
    run_dir = runs_dir / env.invocation_id
    lines = [json.loads(line) for line in (run_dir / "spans.jsonl").read_text().splitlines()]
    report = grounding.lint(
        records_from_jsonl(lines), json.loads((run_dir / "envelope.json").read_text())
    )
    assert report.passed
    assert (run_dir / "grounding.txt").read_text().startswith("grounding: passed")


def test_table_field_types_drive_field_format_targets(runs_dir: Path) -> None:
    profile = DatasetProfile(
        title="Timings",
        keywords=["soil"],
        fields=[
            TableField(name="when", field_type="datetime"),
            TableField(name="how_long", field_type="duration"),
        ],
    )
    env = make_conductor(runs_dir, crate=False).invoke(request("r3.standards-advisor", profile))
    assert env.payload is not None
    assert {i.target for i in env.payload.items if i.kind == RecommendationKind.FIELD_FORMAT} == {
        "field:when",
        "field:how_long",
    }

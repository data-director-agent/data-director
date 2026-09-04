"""Conductor, policy gate, tracing, evidence and grounding linter, using fakes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import fakes
from workbench import grounding
from workbench.agents.abstain import AbstainingStub
from workbench.agents.r3.agent import R3Agent
from workbench.agents.r3.explain import TemplateExplainer
from workbench.conductor import Conductor
from workbench.contract.models import (
    DatasetProfile,
    InvocationRequest,
    OutcomeStatus,
    ReasonCode,
    RecommendationKind,
    TableField,
)
from workbench.evidence import CANONICALISATION, canonicalise, content_hash
from workbench.policy import PROFILES_DIR, PolicyError, gate, load_profile
from workbench.store import RunStore
from workbench.tracing import records_from_jsonl

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def soil_profile() -> DatasetProfile:
    return DatasetProfile.model_validate(
        json.loads((SAMPLES / "soil-chemistry.profile.json").read_text())
    )


def make_conductor(runs_dir: Path, r3: R3Agent | None = None, crate: bool = True) -> Conductor:
    r3 = r3 or R3Agent(retrieval=fakes.FakeRetrieval(), explainer=TemplateExplainer())
    return Conductor(
        agents={r3.agent_id: r3, "stub.abstain": AbstainingStub()},
        store=RunStore(runs_dir),
        write_crate=crate,
    )


def request(
    agent_id: str, profile: DatasetProfile | None = None, bundle: str = "profile:default"
) -> InvocationRequest:
    return InvocationRequest(
        agent_id=agent_id, policy_bundle_ref=bundle, input=profile or soil_profile()
    )


# --- Evidence ---------------------------------------------------------------------------------


def test_canonicalisation_is_order_independent_and_projected() -> None:
    a = {"fairsharing_id": "X", "name": "n", "subjects": ["b", "a"], "extra": 1}
    b = {"subjects": ["a", "b"], "name": "n", "fairsharing_id": "X", "extra": 2}
    assert canonicalise(a) == canonicalise(b)
    assert content_hash(a) == content_hash(b)
    assert CANONICALISATION == "json-sorted-utf8-v1"


# --- Policy -----------------------------------------------------------------------------------


@pytest.mark.requirement("DD-POLICY")
def test_gate_answers_only_two_questions() -> None:
    default = load_profile("profile:default", PROFILES_DIR)
    assert gate(default, "r3.standards-advisor", "advise").allowed
    assert not gate(default, "r3.standards-advisor", "advise").requires_approval
    assert gate(default, "r3.standards-advisor", "deposit").requires_approval
    assert not gate(default, "unknown.agent", "advise").allowed
    restrictive = load_profile("profile:test-restrictive", PROFILES_DIR)
    assert not gate(restrictive, "r3.standards-advisor", "advise").allowed
    assert gate(restrictive, "stub.abstain", "advise").requires_approval


def test_missing_profile_is_a_configuration_error() -> None:
    with pytest.raises(PolicyError):
        load_profile("profile:does-not-exist", PROFILES_DIR)


@pytest.mark.requirement("DD-POLICY", "C13")
def test_disabled_agent_fails_with_problem_details(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, crate=False).invoke(
        request("r3.standards-advisor", bundle="profile:test-restrictive")
    )
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith("/agent-not-permitted")
    assert env.payload is None


@pytest.mark.requirement("DD-POLICY", "DD-OUTCOME", "C13")
def test_action_requiring_approval_is_referred(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, crate=False).invoke(
        request("stub.abstain", bundle="profile:test-restrictive")
    )
    assert env.outcome.status == OutcomeStatus.REFERRED
    assert env.outcome.reason_code == ReasonCode.POLICY_REQUIRES_APPROVAL
    assert env.outcome.referred_to == "data_steward"


# --- Stub -------------------------------------------------------------------------------------


@pytest.mark.requirement("DD-OUTCOME", "R3.6")
def test_stub_abstains_unconditionally(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, crate=False).invoke(request("stub.abstain"))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.CAPABILITY_NOT_IMPLEMENTED
    assert env.requires_human_review is True


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
    hashes = {e.content_hash for e in env.evidence}
    assert all(set(i.evidence_hashes) <= hashes for i in env.payload.items)
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


@pytest.mark.requirement("DD-GROUNDING", "C13", "R10")
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
            assert result.payload is not None
            item = result.payload.items[0].model_copy(
                update={
                    "resource": result.payload.items[0].resource.model_copy(
                        update={"fairsharing_id": "FAIRsharing.smuggled"}
                    )
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


# --- Store and provenance ---------------------------------------------------------------------


@pytest.mark.requirement("R10", "C13")
def test_every_invocation_is_stored_traced_and_crated(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, crate=True)
    a = conductor.invoke(request("stub.abstain"))
    b = conductor.invoke(request("r3.standards-advisor"))
    ids = [e["invocation_id"] for e in conductor.store.iter_envelopes()]
    assert ids == sorted(ids) == [a.invocation_id, b.invocation_id]  # UUIDv7 sorts chronologically
    for env in (a, b):
        run_dir = runs_dir / env.invocation_id
        assert (run_dir / "envelope.json").exists() and (run_dir / "request.json").exists()
        assert (run_dir / "spans.jsonl").exists()
        meta = json.loads((run_dir / "crate" / "ro-crate-metadata.json").read_text())
        graph = {e["@id"]: e for e in meta["@graph"]}
        assert graph["./"]["conformsTo"]["@id"].startswith("https://w3id.org/ro/wfrun/process/")
        action = graph["#" + env.invocation_id]
        assert action["@type"] == "CreateAction"
        assert action["instrument"]["@id"].endswith(env.agent_id)


# Deliberately not marked P14: the slots exist and say not_measured; the footprint is not captured.
def test_energy_footprint_slots_are_present_but_honestly_not_measured(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, crate=False).invoke(request("stub.abstain"))
    doc = env.to_document()
    assert doc["telemetry"]["energy_method"] == "not_measured"
    assert doc["telemetry"]["energy_estimate_j"] is None


def test_unknown_agent_is_a_caller_error(runs_dir: Path) -> None:
    from workbench.conductor import UnknownAgent

    with pytest.raises(UnknownAgent):
        make_conductor(runs_dir, crate=False).invoke(request("nope"))


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

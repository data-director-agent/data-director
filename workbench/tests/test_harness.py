"""Conductor, policy gate, input check, tracing, evidence and grounding linter, using scripted
agents. Nothing here depends on a real agent; see test_quality.py, test_factcheck.py and the
xfailed test_r3_harness.py for those."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dd_agent_stub.agent import AbstainingStub
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import (
    Claim,
    DatasetProfile,
    GroundingMode,
    InvocationRequest,
    MetadataRecord,
    Outcome,
    OutcomeStatus,
    QualityReview,
    ReasonCode,
    to_document,
)
from dd_sdk.contract.validate import validate_envelope
from dd_sdk.evidence import (
    CANONICALISATION,
    INPUT_CANONICALISATION,
    canonicalise,
    content_hash,
    input_hash,
)
from dd_sdk.tracing import records_from_jsonl
from workbench import grounding
from workbench import testing as fakes
from workbench.conductor import DuplicateInvocation
from workbench.policy import DEFAULT_PROFILE, PolicyError, gate, load_profile
from workbench.store import RunStore
from workbench.testing import (
    RESTRICTIVE,
    SOURCE_A,
    SOURCE_B,
    TEST_PRINCIPAL,
    Chat,
    ScriptedAgent,
    make_conductor,
    request,
)

# --- Evidence ---------------------------------------------------------------------------------


@pytest.mark.requirement("DD-EVIDENCE")
def test_fairsharing_canonicalisation_is_order_independent_and_projected() -> None:
    a = {"fairsharing_id": "X", "name": "n", "subjects": ["b", "a"], "extra": 1}
    b = {"subjects": ["a", "b"], "name": "n", "fairsharing_id": "X", "extra": 2}
    assert canonicalise(a) == canonicalise(b)
    assert content_hash(a) == content_hash(b)
    assert CANONICALISATION == "json-sorted-utf8-v1"


@pytest.mark.requirement("DD-EVIDENCE")
def test_input_hash_is_stable_across_key_order_and_sensitive_to_list_order() -> None:
    a = {"schema_class": "MetadataRecord", "creators": ["x", "y"], "title": "t"}
    b = {"title": "t", "creators": ["x", "y"], "schema_class": "MetadataRecord"}
    assert input_hash(a) == input_hash(b) == content_hash(a, INPUT_CANONICALISATION)
    assert input_hash(a) != input_hash({**a, "creators": ["y", "x"]})


def test_unknown_canonicalisation_is_a_programmer_error() -> None:
    with pytest.raises(ValueError, match="unknown canonicalisation"):
        content_hash({}, "nope")


# --- Policy -----------------------------------------------------------------------------------


@pytest.mark.requirement("DD-POLICY")
def test_gate_matches_the_class_the_profile_assigns_not_the_one_the_agent_declares() -> None:
    default = load_profile(DEFAULT_PROFILE)
    assert gate(default, "quality.reviewer", "advise").allowed
    assert not gate(default, "quality.reviewer", "advise").requires_approval
    assert not gate(default, "unknown.agent", "advise").allowed
    # An agent that declares a class other than the one the steward assigned is refused, not
    # gated on its own claim: here a reviewer that starts declaring writes.
    upgraded = gate(default, "quality.reviewer", "metadata_write")
    assert not upgraded.allowed and upgraded.refusal == "action-class-mismatch"
    restrictive = load_profile(RESTRICTIVE)
    assert gate(restrictive, "stub.abstain", "advise").requires_approval
    # The steward assigned `deposit`; the agent declaring `advise` cannot talk its way down.
    downgraded = gate(restrictive, "quality.reviewer", "advise")
    assert not downgraded.allowed and downgraded.refusal == "action-class-mismatch"


def test_missing_profile_is_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(PolicyError):
        load_profile(tmp_path / "does-not-exist.yaml")


@pytest.mark.requirement("DD-POLICY")
def test_a_profile_key_nothing_enforces_is_refused(tmp_path: Path) -> None:
    stale = tmp_path / "stale.yaml"
    stale.write_text(
        DEFAULT_PROFILE.read_text(encoding="utf-8") + "approved_repositories: []\n",
        encoding="utf-8",
    )
    with pytest.raises(PolicyError, match="approved_repositories"):
        load_profile(stale)


@pytest.mark.requirement("DD-POLICY", "C13.2")
def test_disabled_agent_fails_with_problem_details(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.INPUT_ONLY, fakes.review_of_input)
    env = make_conductor(runs_dir, agent, profile=RESTRICTIVE).invoke(
        request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith("/agent-not-permitted")
    assert env.payload is None and agent.calls == 0


@pytest.mark.requirement("DD-POLICY")
def test_an_agent_declaring_another_class_than_assigned_fails_and_is_not_run(
    runs_dir: Path,
) -> None:
    agent = ScriptedAgent(
        GroundingMode.INPUT_ONLY, fakes.review_of_input, agent_id="quality.reviewer"
    )
    env = make_conductor(runs_dir, agent, profile=RESTRICTIVE).invoke(
        request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith("/action-class-mismatch")
    assert env.problem.http_status == 403
    assert "'deposit'" in (env.problem.detail or "") and agent.calls == 0


@pytest.mark.requirement("DD-POLICY", "DD-OUTCOME", "C13.2")
def test_action_requiring_approval_is_referred(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, AbstainingStub(), profile=RESTRICTIVE).invoke(
        request("stub.abstain"), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.REFERRED
    assert env.outcome.reason_code == ReasonCode.POLICY_REQUIRES_APPROVAL
    assert env.outcome.referred_to == "data_steward"


@pytest.mark.requirement("DD-POLICY-OWNER")
def test_the_envelope_records_the_profile_the_conductor_applied(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, AbstainingStub(), profile=RESTRICTIVE)
    env = conductor.invoke(request("stub.abstain"), acting_for=TEST_PRINCIPAL)
    assert env.policy_bundle_ref == "profile:test-restrictive@v2"
    assert env.policy_digest == hashlib.sha256(RESTRICTIVE.read_bytes()).hexdigest()
    stored = conductor.store.get(env.invocation_id)
    assert stored is not None and stored["policy_digest"] == env.policy_digest


@pytest.mark.requirement("DD-ACTS-FOR")
def test_the_envelope_records_whom_the_invocation_acted_for(runs_dir: Path) -> None:
    disabled = ScriptedAgent(GroundingMode.NONE, fakes.review_of_input, agent_id="fake.disabled")
    conductor = make_conductor(runs_dir, AbstainingStub(), disabled)
    ran = conductor.invoke(request("stub.abstain"), acting_for=TEST_PRINCIPAL)
    refused = conductor.invoke(request("fake.disabled"), acting_for=TEST_PRINCIPAL)
    # A refused action was still attempted on someone's behalf.
    assert refused.outcome.status == OutcomeStatus.FAILED
    for env in (ran, refused):
        assert env.acting_for == TEST_PRINCIPAL
        stored = conductor.store.get(env.invocation_id)
        assert stored is not None and stored["acting_for"] == to_document(TEST_PRINCIPAL)
        assert stored["acting_for"]["assurance"] == "asserted"


# --- Input check ------------------------------------------------------------------------------


@pytest.mark.requirement("DD-INPUT-ACCEPTS")
def test_input_of_an_unaccepted_class_is_a_failed_outcome_and_the_agent_is_not_run(
    runs_dir: Path,
) -> None:
    agent = ScriptedAgent(GroundingMode.INPUT_ONLY, fakes.review_of_input)  # accepts MetadataRecord
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id, fakes.claim()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith("/input-not-accepted")
    assert env.problem.http_status == 422
    assert "MetadataRecord" in (env.problem.detail or "") and "Claim" in (env.problem.detail or "")
    assert agent.calls == 0
    assert conductor.store.get(env.invocation_id) is not None  # refusals are stored too


@pytest.mark.requirement("DD-INPUT-ACCEPTS")
def test_an_agent_may_accept_several_input_classes(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.NONE, fakes.review_of_input)  # MetadataRecord or Profile
    conductor = make_conductor(runs_dir, agent)
    for inp in (fakes.record(), DatasetProfile(title="t")):
        assert conductor.invoke(
            request(agent.spec.agent_id, inp), acting_for=TEST_PRINCIPAL
        ).outcome.status == (OutcomeStatus.SUCCEEDED)
    assert conductor.invoke(
        request(agent.spec.agent_id, Claim(text="x")), acting_for=TEST_PRINCIPAL
    ).outcome.status == (OutcomeStatus.FAILED)


@pytest.mark.requirement("DD-OUTCOME")
def test_stub_accepts_every_input_class_and_abstains(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, AbstainingStub())
    for inp in (fakes.record(), fakes.claim(), DatasetProfile()):
        env = conductor.invoke(request("stub.abstain", inp), acting_for=TEST_PRINCIPAL)
        assert env.outcome.status == OutcomeStatus.ABSTAINED
        assert env.outcome.reason_code == ReasonCode.CAPABILITY_NOT_IMPLEMENTED
        assert env.grounding_mode == GroundingMode.NONE
        assert env.requires_human_review is True


# --- Agent contract ---------------------------------------------------------------------------


def test_agent_exception_becomes_failed_outcome(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.NONE, RuntimeError("boom"))
    env = make_conductor(runs_dir, agent).invoke(
        request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith("/agent-error")
    assert "boom" in (env.problem.detail or "")


def test_payload_of_the_wrong_class_is_a_failed_outcome(runs_dir: Path) -> None:
    """An agent contradicting its own specification is a programmer error, not a content outcome."""
    agent = ScriptedAgent(
        GroundingMode.RETRIEVAL,
        fakes.fact_check_over(SOURCE_A),
        steps=[SOURCE_A],
        payload_type=QualityReview,
    )
    env = make_conductor(runs_dir, agent).invoke(
        request(agent.spec.agent_id, fakes.claim()), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and "declared QualityReview" in (env.problem.detail or "")


def _without_reason(request: InvocationRequest, ctx: RunContext) -> AgentResult:
    return AgentResult(outcome=Outcome(status=OutcomeStatus.ABSTAINED, statement="No reason."))


def _succeeded_without_payload(request: InvocationRequest, ctx: RunContext) -> AgentResult:
    return AgentResult(outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Nothing."))


def _failed_without_problem(request: InvocationRequest, ctx: RunContext) -> AgentResult:
    return AgentResult(outcome=Outcome(status=OutcomeStatus.FAILED, statement="Gave up."))


def _unregistered_canonicalisation(request: InvocationRequest, ctx: RunContext) -> AgentResult:
    result = fakes.review_of_input(request, ctx)
    evidence = [e.model_copy(update={"canonicalisation": "unregistered"}) for e in result.evidence]
    return AgentResult(outcome=result.outcome, payload=result.payload, evidence=evidence)


@pytest.mark.parametrize(
    ("behaviour", "problem"),
    [
        (_without_reason, "agent-error"),
        (_succeeded_without_payload, "grounding-violation"),  # the linter withholds it first
        (_failed_without_problem, "agent-error"),
        (_unregistered_canonicalisation, "agent-error"),
    ],
    ids=lambda b: getattr(b, "__name__", "").strip("_") or None,
)
def test_a_result_that_breaks_the_contract_is_a_stored_failed_outcome(
    runs_dir: Path, behaviour: fakes.Behaviour, problem: str
) -> None:
    """A remote agent's contract violation is its own error: stored, never raised past the store."""
    agent = ScriptedAgent(GroundingMode.NONE, behaviour)
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith(f"/{problem}")
    stored = conductor.store.get(env.invocation_id)
    assert stored is not None
    validate_envelope(stored)


def test_unknown_agent_is_a_caller_error(runs_dir: Path) -> None:
    from workbench.conductor import UnknownAgent

    with pytest.raises(UnknownAgent):
        make_conductor(runs_dir).invoke(request("nope"), acting_for=TEST_PRINCIPAL)


# --- Grounding through the conductor ----------------------------------------------------------


@pytest.mark.requirement("DD-GROUNDING-MODE", "C13.1")
def test_conductor_records_the_declared_mode_on_envelope_and_root_span(runs_dir: Path) -> None:
    for mode, behaviour, inp in (
        (GroundingMode.INPUT_ONLY, fakes.review_of_input, fakes.record()),
        (GroundingMode.NONE, fakes.review_of_input, fakes.record()),
        (GroundingMode.RETRIEVAL, fakes.fact_check_over(SOURCE_A), fakes.claim()),
    ):
        agent = ScriptedAgent(
            mode, behaviour, steps=[SOURCE_A] if mode.value == "retrieval" else []
        )
        conductor = make_conductor(runs_dir / mode.value, agent)
        env = conductor.invoke(request(agent.spec.agent_id, inp), acting_for=TEST_PRINCIPAL)
        assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
        assert env.grounding_mode == mode
        report = conductor.grounding_reports[env.invocation_id]
        assert report.passed and report.mode == mode.value
        spans = (runs_dir / mode.value / env.invocation_id / "spans.jsonl").read_text()
        stored = records_from_jsonl([json.loads(line) for line in spans.splitlines()])
        root = next(r for r in stored if r.name == "invoke_agent")
        assert root.attributes["dd.grounding_mode"] == mode.value
        assert root.attributes["dd.input_hash"] == input_hash(
            conductor.store.get_request(env.invocation_id)["input"]  # type: ignore[index]
        )


@pytest.mark.requirement("DD-GROUNDING-MODE")
def test_input_only_agent_may_call_a_model_without_retrieving(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.INPUT_ONLY, fakes.review_of_input, steps=[Chat()])
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    assert conductor.grounding_reports[env.invocation_id].chat_count == 1


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDING")
def test_none_agent_that_calls_a_model_is_withheld(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.NONE, fakes.review_of_input, steps=[Chat()])
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith("/grounding-violation")
    assert env.payload is None and env.evidence == []
    assert any(
        v.startswith("N1") for v in conductor.grounding_reports[env.invocation_id].violations
    )


@pytest.mark.requirement("DD-GROUNDING-MODE")
def test_input_only_agent_that_retrieves_is_withheld(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.INPUT_ONLY, fakes.review_of_input, steps=[SOURCE_A])
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.FAILED
    assert any(
        v.startswith("R1") for v in conductor.grounding_reports[env.invocation_id].violations
    )


@pytest.mark.requirement("DD-GROUNDING", "C13.1", "R10.1")
def test_retrieval_agent_passes_when_it_rests_only_on_what_it_retrieved(runs_dir: Path) -> None:
    agent = ScriptedAgent(
        GroundingMode.RETRIEVAL,
        fakes.fact_check_over(SOURCE_A, SOURCE_B),
        steps=[SOURCE_A, SOURCE_B, Chat()],
    )
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id, fakes.claim()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    report = conductor.grounding_reports[env.invocation_id]
    assert report.passed and (report.retrieval_count, report.chat_count) == (2, 1)
    assert env.telemetry.trace_id and len(env.telemetry.trace_id) == 32


@pytest.mark.requirement("DD-GROUNDING", "DD-GROUNDED-PAYLOAD")
def test_identity_not_retrieved_is_withheld(runs_dir: Path) -> None:
    """A payload resting on something never retrieved must not leave the system."""
    agent = ScriptedAgent(
        GroundingMode.RETRIEVAL, fakes.fact_check_over(SOURCE_A, SOURCE_B), steps=[SOURCE_A]
    )
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id, fakes.claim()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith("/grounding-violation")
    assert env.payload is None
    violations = conductor.grounding_reports[env.invocation_id].violations
    assert any(v.startswith("G2") and "'src:b'" in v for v in violations)


@pytest.mark.requirement("DD-GROUNDING")
def test_chat_before_retrieval_fails_g1(runs_dir: Path) -> None:
    agent = ScriptedAgent(
        GroundingMode.RETRIEVAL, fakes.fact_check_over(SOURCE_A), steps=[Chat(), SOURCE_A]
    )
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id, fakes.claim()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.FAILED
    assert any(
        v.startswith("G1") for v in conductor.grounding_reports[env.invocation_id].violations
    )


@pytest.mark.requirement("R10.1")
def test_linter_runs_offline_over_written_spans(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.INPUT_ONLY, fakes.review_of_input, steps=[Chat()])
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL)
    run_dir = runs_dir / env.invocation_id
    lines = [json.loads(line) for line in (run_dir / "spans.jsonl").read_text().splitlines()]
    report = grounding.lint(
        records_from_jsonl(lines), json.loads((run_dir / "envelope.json").read_text())
    )
    assert report.passed and report.mode == "input_only"
    assert (run_dir / "grounding.txt").read_text().startswith("grounding: passed [input_only]")


# --- Store and provenance ---------------------------------------------------------------------


@pytest.mark.requirement("R10.1", "C13.1")
def test_every_invocation_is_stored_traced_and_crated(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.NONE, fakes.review_of_input)
    conductor = make_conductor(runs_dir, agent, AbstainingStub(), crate=True)
    a = conductor.invoke(request("stub.abstain"), acting_for=TEST_PRINCIPAL)
    b = conductor.invoke(request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL)
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


@pytest.mark.requirement("DD-ACTS-FOR", "R10.1")
def test_the_crate_names_the_human_beside_the_agent(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, AbstainingStub(), crate=True)
    env = conductor.invoke(request("stub.abstain"), acting_for=TEST_PRINCIPAL)
    meta = json.loads(
        (runs_dir / env.invocation_id / "crate" / "ro-crate-metadata.json").read_text()
    )
    graph = {e["@id"]: e for e in meta["@graph"]}
    action = graph["#" + env.invocation_id]
    assert action["agent"] == {"@id": TEST_PRINCIPAL.principal_id}
    person = graph[TEST_PRINCIPAL.principal_id]
    assert person["@type"] == "Person" and person["name"] == TEST_PRINCIPAL.name
    assert "asserted" in person["description"]


@pytest.mark.requirement("R10.1")
def test_a_reused_invocation_id_is_refused_and_the_stored_run_kept(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, AbstainingStub())
    req = request("stub.abstain")
    first = conductor.invoke(req, acting_for=TEST_PRINCIPAL)
    envelope_path = runs_dir / first.invocation_id / "envelope.json"
    stored = envelope_path.read_bytes()
    report = conductor.grounding_reports[first.invocation_id]

    with pytest.raises(DuplicateInvocation, match=first.invocation_id):
        conductor.invoke(req, acting_for=TEST_PRINCIPAL)
    assert envelope_path.read_bytes() == stored
    assert conductor.grounding_reports[first.invocation_id] is report
    assert [e["invocation_id"] for e in conductor.store.iter_envelopes()] == [first.invocation_id]


def test_the_store_never_overwrites_a_run(tmp_path: Path) -> None:
    env = make_conductor(tmp_path, AbstainingStub()).invoke(
        request("stub.abstain"), acting_for=TEST_PRINCIPAL
    )
    with pytest.raises(FileExistsError):
        RunStore(tmp_path).append(env.to_document())


# Deliberately not marked P14: the slots exist and say not_measured; the footprint is not captured.
def test_energy_footprint_slots_are_present_but_honestly_not_measured(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, AbstainingStub()).invoke(
        request("stub.abstain"), acting_for=TEST_PRINCIPAL
    )
    doc = env.to_document()
    assert doc["telemetry"]["energy_method"] == "not_measured"
    assert doc["telemetry"]["energy_estimate_j"] is None


def test_scripted_specs_accept_what_their_tests_assume() -> None:
    assert fakes.SPECS[GroundingMode.INPUT_ONLY].accepts == (MetadataRecord,)
    assert fakes.SPECS[GroundingMode.RETRIEVAL].accepts == (Claim,)


def test_the_conductor_keeps_no_spans_after_a_run_and_caps_its_reports(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A long-running `workbench serve` must not grow with every invocation."""
    monkeypatch.setattr("workbench.conductor.GROUNDING_REPORTS_KEPT", 1)
    conductor = make_conductor(runs_dir, ScriptedAgent(GroundingMode.NONE, fakes.review_of_input))
    first = conductor.invoke(request("fake.none", fakes.record()), acting_for=TEST_PRINCIPAL)
    second = conductor.invoke(request("fake.none", fakes.record()), acting_for=TEST_PRINCIPAL)
    assert conductor.tracing.memory.get_finished_spans() == []
    assert conductor.tracing.imported == {}
    assert list(conductor.grounding_reports) == [second.invocation_id]
    assert (runs_dir / first.invocation_id / "grounding.txt").exists()

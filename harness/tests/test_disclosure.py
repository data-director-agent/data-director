"""Model calls, prompts and the disclosure of a project's documents (docs/specs/disclosure.md)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import rdflib
from rdflib.namespace import PROV, RDF

from dd_harness.conductor import Conductor
from dd_harness.disclosure import IPTC, disclose
from dd_harness.projects import Decision, ProjectStore, text_digest
from dd_harness.testing import (
    TEST_PRINCIPAL,
    DocumentStub,
    ProbeReview,
    ScriptedAgent,
    document_request,
    make_conductor,
    record,
    request,
)
from dd_sdk.agent import AgentResult
from dd_sdk.contract.models import (
    DocumentKind,
    Envelope,
    EvidenceItem,
    GroundingMode,
    GroundingRef,
    ModelAccount,
    Outcome,
    OutcomeStatus,
    Principal,
)
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION
from dd_sdk.prompts import ModelCallLog, prompt_digest

MODEL = "test-model-2026-11-01"
DECIDER = Principal(principal_id="https://orcid.org/0000-0002-1825-0097", name="Josiah Carberry")
SCHEMA = rdflib.Namespace("http://schema.org/")


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project(store: ProjectStore) -> str:
    return store.create(acted_for=TEST_PRINCIPAL, caused_by="test")


def drafted(
    conductor: Conductor, store: ProjectStore, project: str, kind: DocumentKind
) -> Envelope:
    envelope = conductor.invoke(
        request("stub.document", document_request(kind)), acting_for=TEST_PRINCIPAL
    )
    assert envelope.outcome.status == OutcomeStatus.SUCCEEDED, envelope.outcome.statement
    store.record_draft(project, envelope)
    return envelope


def decide(store: ProjectStore, project: str, kind: DocumentKind, **given: Any) -> None:
    (document,) = [d for d in store.documents(project) if d["document_kind"] == kind.value]
    shown = document["versions"][-1]
    store.decide(
        project,
        Decision(
            document_id=shown["document_id"],
            version=shown["version"],
            digest=text_digest(shown["text"]),
            **given,
        ),
        acted_for=DECIDER,
        caused_by="test",
    )


@pytest.mark.requirement("C13.4")
@pytest.mark.parametrize("remote", [True, False])
def test_a_model_call_is_in_the_envelope_and_its_prompt_beside_it_only(
    runs_dir: Path, remote: bool
) -> None:
    conductor = make_conductor(runs_dir, DocumentStub(MODEL), crate=True, remote=remote)
    envelope = conductor.invoke(
        request("stub.document", document_request()), acting_for=TEST_PRINCIPAL
    )
    assert envelope.outcome.status == OutcomeStatus.SUCCEEDED, envelope.outcome.statement
    (call,) = envelope.telemetry.model_calls
    assert (call.model_provider, call.model_id) == ("test", MODEL)
    assert (call.input_tokens, call.output_tokens) == (12, 34)
    # No broker answered, so the deployment paid (docs/specs/model-accounts.md).
    assert call.model_account is ModelAccount.DEPLOYMENT

    prompts = conductor.store.get_prompts(envelope.invocation_id)
    assert list(prompts) == [call.prompt_digest]
    assert prompt_digest(prompts[call.prompt_digest]) == call.prompt_digest
    run_dir = runs_dir / envelope.invocation_id
    prompt_text = "Draft the document asked for."
    for kept in ("envelope.json", "spans.jsonl", "crate/ro-crate-metadata.json"):
        assert prompt_text not in (run_dir / kept).read_text(encoding="utf-8"), kept

    crate = json.loads((run_dir / "crate" / "ro-crate-metadata.json").read_text(encoding="utf-8"))
    by_id = {e["@id"]: e for e in crate["@graph"]}
    prompt = by_id[f"#prompt-{call.prompt_digest}"]
    assert prompt["sha256"] == call.prompt_digest
    (action,) = [e for e in crate["@graph"] if e.get("object") == [{"@id": prompt["@id"]}]]
    assert by_id[action["instrument"]["@id"]]["name"] == MODEL


def test_a_run_without_a_model_lists_no_calls_and_keeps_no_prompts(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, DocumentStub())
    envelope = conductor.invoke(
        request("stub.document", document_request()), acting_for=TEST_PRINCIPAL
    )
    assert "model_calls" not in envelope.to_document()["telemetry"]
    assert conductor.store.get_prompts(envelope.invocation_id) == {}


def _scripted(calls: ModelCallLog, prompts: dict[str, Any]) -> ScriptedAgent:
    def behaviour(_: Any, ctx: Any) -> AgentResult:
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Reviewed."),
            payload=ProbeReview(
                score=1.0,
                grounded_on=[GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)],
            ),
            evidence=[
                EvidenceItem(
                    source_id=ctx.input_ref,
                    hash_algorithm=HASH_ALGORITHM,
                    canonicalisation=INPUT_CANONICALISATION,
                    content_hash=ctx.input_hash,
                )
            ],
            model_calls=calls.calls,
            prompts=prompts,
        )

    return ScriptedAgent(GroundingMode.INPUT_ONLY, behaviour)


@pytest.mark.requirement("C13.4")
@pytest.mark.parametrize(
    ("tamper", "expected"),
    [
        ("missing", "model calls whose prompt was not returned"),
        ("altered", "prompts that do not hash to their digest"),
        ("extra", "prompts no model call names"),
    ],
)
def test_prompts_that_are_not_those_the_calls_name_fail_the_run(
    runs_dir: Path, tamper: str, expected: str
) -> None:
    calls = ModelCallLog("test")
    calls.record({"messages": [{"role": "user", "content": "Review."}]}, MODEL)
    prompts: dict[str, Any] = dict(calls.prompts)
    (digest,) = prompts
    if tamper == "missing":
        prompts = {}
    elif tamper == "altered":
        prompts[digest] = {"messages": [{"role": "user", "content": "Something else."}]}
    else:
        other: dict[str, Any] = {"messages": []}
        prompts[prompt_digest(other)] = other
    conductor = make_conductor(runs_dir, _scripted(calls, prompts))
    envelope = conductor.invoke(request("fake.input-only", record()), acting_for=TEST_PRINCIPAL)
    assert envelope.outcome.status == OutcomeStatus.FAILED
    assert envelope.problem is not None and envelope.problem.type.endswith("agent-error")
    assert expected in envelope.outcome.statement
    # The calls happened, so they are recorded; only a prompt that is what a call names is kept.
    assert [c.prompt_digest for c in envelope.telemetry.model_calls] == [digest]
    kept = conductor.store.get_prompts(envelope.invocation_id)
    assert set(kept) <= {digest}
    assert all(prompt_digest(p) == d for d, p in kept.items())


@pytest.mark.requirement("R10.2")
def test_the_disclosure_says_how_each_approved_document_came_about(
    runs_dir: Path, store: ProjectStore, project: str
) -> None:
    by_model = make_conductor(runs_dir, DocumentStub(MODEL))
    by_rule = make_conductor(runs_dir, DocumentStub())
    readme = drafted(by_model, store, project, DocumentKind.README)
    drafted(by_model, store, project, DocumentKind.METADATA_RECORD)
    drafted(by_rule, store, project, DocumentKind.DATA_DICTIONARY)
    decide(store, project, DocumentKind.README, verdict="approved")
    decide(
        store,
        project,
        DocumentKind.METADATA_RECORD,
        verdict="approved",
        edited_text="A record a person corrected.\n",
        reason="The title was wrong.",
    )
    decide(store, project, DocumentKind.DATA_DICTIONARY, verdict="approved")

    found = disclose(store, by_model.store, project)
    origins = {d.document_kind: d.origin for d in found.documents}
    assert origins == {
        "readme": "model",
        "metadata_record": "model_revised",
        "data_dictionary": "template",
    }
    (readme_disclosure,) = [d for d in found.documents if d.document_kind == "readme"]
    assert readme_disclosure.draft is not None
    assert readme_disclosure.draft.invocation_id == readme.invocation_id
    (model_used,) = readme_disclosure.draft.models
    assert model_used.model_id == MODEL
    assert model_used.prompt_digest == readme.telemetry.model_calls[0].prompt_digest

    statement = found.statement()
    assert (
        "Of the 3 approved documents of this project, 2 were drafted with generative AI"
        in statement
    )
    assert f"{MODEL} (test)" in statement
    assert "reproduced verbatim" in statement
    assert "Josiah Carberry" in statement
    assert "The title was wrong." in statement
    assert "no generative AI" in statement  # the document drafted by rule
    assert model_used.prompt_digest in statement


@pytest.mark.requirement("R10.2")
def test_only_approved_versions_are_disclosed(
    runs_dir: Path, store: ProjectStore, project: str
) -> None:
    conductor = make_conductor(runs_dir, DocumentStub(MODEL))
    drafted(conductor, store, project, DocumentKind.README)
    drafted(conductor, store, project, DocumentKind.METADATA_RECORD)
    decide(store, project, DocumentKind.README, verdict="rejected", reason="Not ours.")

    found = disclose(store, conductor.store, project)
    assert found.documents == ()
    assert found.pending == 1
    statement = found.statement()
    assert "\n## " not in statement  # no document is described
    assert "1 other document" in statement


def test_a_template_only_project_says_no_generative_model_was_used(
    runs_dir: Path, store: ProjectStore, project: str
) -> None:
    conductor = make_conductor(runs_dir, DocumentStub())
    drafted(conductor, store, project, DocumentKind.README)
    decide(store, project, DocumentKind.README, verdict="approved")
    statement = disclose(store, conductor.store, project).statement()
    assert "No generative AI model was used" in statement


# rdflib's JSON-LD parser builds a ConjunctiveGraph internally, whatever graph it is given.
@pytest.mark.requirement("R10.2")
@pytest.mark.filterwarnings("ignore:ConjunctiveGraph is deprecated:DeprecationWarning")
def test_the_disclosure_reads_as_prov_o(runs_dir: Path, store: ProjectStore, project: str) -> None:
    conductor = make_conductor(runs_dir, DocumentStub(MODEL))
    readme = drafted(conductor, store, project, DocumentKind.README)
    decide(
        store,
        project,
        DocumentKind.README,
        verdict="approved",
        edited_text="Edited.\n",
        reason="Clearer.",
    )
    found = disclose(store, conductor.store, project)
    graph = rdflib.Graph().parse(data=json.dumps(found.prov_jsonld()), format="json-ld")

    (document,) = found.documents
    draft_id = rdflib.URIRef(f"urn:uuid:{document.document_id}#v1")
    approved_id = rdflib.URIRef(f"urn:uuid:{document.document_id}#v2")
    run = rdflib.URIRef(f"urn:uuid:{readme.invocation_id}")
    person = rdflib.URIRef(DECIDER.principal_id)

    assert (draft_id, PROV.wasGeneratedBy, run) in graph
    assert (approved_id, PROV.wasRevisionOf, draft_id) in graph
    assert (approved_id, PROV.wasAttributedTo, person) in graph
    assert (person, RDF.type, PROV.Person) in graph
    assert (
        approved_id,
        SCHEMA.digitalSourceType,
        rdflib.URIRef(IPTC + "compositeWithTrainedAlgorithmicMedia"),
    ) in graph
    plans = list(graph.objects(None, PROV.hadPlan))
    assert len(plans) == 1 and (plans[0], RDF.type, PROV.Plan) in graph
    approvals = list(graph.subjects(PROV.used, approved_id))
    assert len(approvals) == 1
    assert (approvals[0], PROV.wasAssociatedWith, person) in graph

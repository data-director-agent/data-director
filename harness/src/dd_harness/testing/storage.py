"""Conformance checks for a storage backend (docs/specs/storage.md).

Each check holds a backend to one guarantee `RunStorage` or `ProjectStorage` states, through the
protocol alone, so any backend can run them: the file backends in the harness's own tests, and a
database backend in its own package. A check takes `make`, which opens a store by name. The same
name opens the same store again, as after a restart; another name opens an empty one.

    def test_my_run_storage(tmp_path):
        check_run_storage(lambda name: MyRunStore(f"{database}/{name}"))

`RUN_STORAGE_CHECKS` and `PROJECT_STORAGE_CHECKS` name each check, for a test that reports them
one by one.
"""

from __future__ import annotations

import hashlib
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dd_harness.projects import (
    APPROVED,
    CONVERSATION_STARTED,
    DOCUMENT_CHANGE_REFUSED,
    DOCUMENT_QUESTION_ANSWERED,
    DOCUMENT_VERSION_DECIDED,
    INVENTORY_ADDED,
    PACKAGE_BUILT,
    PROJECT_CREATED,
    PROJECT_VALIDATED,
    REJECTED,
    ChangeRefusedError,
    Decision,
    ProjectError,
    Refusal,
    UnknownProjectError,
    Verdict,
    text_digest,
)
from dd_harness.storage import ProjectStorage, RunStorage
from dd_harness.testing.classes import ProbeClaim
from dd_harness.testing.doubles import STUB_QUESTION, DocumentStub
from dd_harness.testing.fixtures import TEST_PRINCIPAL, document_request, request
from dd_harness.testing.serving import make_conductor
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    DocumentKind,
    DraftAnswer,
    DraftRequest,
    Envelope,
    FileInventory,
    IdentificationMethod,
    InventoryFile,
    new_invocation_id,
)
from dd_sdk.evidence import input_hash

type MakeRunStorage = Callable[[str], RunStorage]
type MakeProjectStorage = Callable[[str], ProjectStorage]

# A well-formed identifier that names nothing stored.
NOWHERE = "0" * 8 + "-0000-7000-8000-" + "0" * 12
# Names that must never reach outside a run.
MALFORMED_ARTIFACTS = ("", "/etc/passwd", "../escape", "a/../../escape", "a//b", "envelope.json")


@contextmanager
def _raises(kind: type[Exception], what: str) -> Iterator[None]:
    """Fails unless the block raises `kind`; `what` says what should have been refused."""
    try:
        yield
    except kind:
        return
    raise AssertionError(f"{what}: expected {kind.__name__}")


def _named[S](make: Callable[[str], S], n: int) -> Callable[[str], S]:
    """`make`, with names of the check's own, so that no two checks share a store."""

    def named(name: str) -> S:
        return make(f"check-{n}-{name}")

    return named


# --- Runs ----------------------------------------------------------------------------------------


def stored_envelope(
    conversation_id: str | None = None, parent_invocation_id: str | None = None
) -> dict[str, Any]:
    """An envelope document with the fields a backend might index. `append` stores what it is
    given; the conductor has already checked it against the contract."""
    return {
        "invocation_id": new_invocation_id(),
        "agent_id": "stub.storage",
        "agent_version": "0.1.0",
        "conversation_id": conversation_id,
        "parent_invocation_id": parent_invocation_id,
        "project_id": None,
        "completed_at": datetime.now(UTC).isoformat(),
        "outcome": {"status": "succeeded", "statement": "Stored for a storage check."},
    }


def check_a_run_is_written_once(make: MakeRunStorage) -> None:
    store = make("runs")
    envelope = stored_envelope()
    run_id = envelope["invocation_id"]
    assert not store.has(run_id)
    assert store.get(run_id) is None and store.get_request(run_id) is None
    store.append(envelope, {"agent_id": "stub.storage", "input": {"n": 1}})
    assert store.has(run_id)
    assert store.get(run_id) == envelope
    assert store.get_request(run_id) == {"agent_id": "stub.storage", "input": {"n": 1}}
    with _raises(FileExistsError, "a run written twice"):
        store.append({**envelope, "agent_version": "9.9.9"}, {"input": {"n": 2}})
    assert store.get(run_id) == envelope
    assert store.get_request(run_id) == {"agent_id": "stub.storage", "input": {"n": 1}}
    assert [e["invocation_id"] for e in store.iter_envelopes()] == [run_id]
    # Reopened, as after a restart, the store holds the same run.
    assert make("runs").get(run_id) == envelope


def check_envelopes_come_back_in_the_order_stored(make: MakeRunStorage) -> None:
    store = make("runs")
    envelopes = [stored_envelope() for _ in range(5)]
    for envelope in envelopes:
        store.append(envelope)
    expected = [e["invocation_id"] for e in envelopes]
    assert [e["invocation_id"] for e in store.iter_envelopes()] == expected
    assert [e["invocation_id"] for e in make("runs").iter_envelopes()] == expected


def check_envelopes_are_found_by_conversation(make: MakeRunStorage) -> None:
    store = make("runs")
    first, other = new_invocation_id(), new_invocation_id()
    turn = stored_envelope(first)
    child = stored_envelope(first, parent_invocation_id=turn["invocation_id"])
    elsewhere = stored_envelope(other)
    alone = stored_envelope()
    later = stored_envelope(first)
    for envelope in (turn, child, elsewhere, alone, later):
        store.append(envelope)
    found = [e["invocation_id"] for e in store.iter_envelopes(conversation_id=first)]
    assert found == [turn["invocation_id"], child["invocation_id"], later["invocation_id"]]
    assert list(store.iter_envelopes(conversation_id=NOWHERE)) == []
    assert len(list(store.iter_envelopes())) == 5


def check_artifacts_are_kept_once_beside_their_run(make: MakeRunStorage) -> None:
    store = make("runs")
    envelope = stored_envelope()
    run_id = envelope["invocation_id"]
    with _raises(KeyError, "an artifact for a run not stored"):
        store.put_artifact(run_id, "spans.jsonl", b"{}\n")
    store.append(envelope)
    store.put_artifact(run_id, "spans.jsonl", b'{"name": "invoke_agent"}\n')
    store.put_artifact(run_id, "crate/ro-crate-metadata.json", b'{"@graph": []}')
    store.put_artifact(run_id, "crate/sub/file.bin", bytes(range(256)))
    assert store.get_artifact(run_id, "spans.jsonl") == b'{"name": "invoke_agent"}\n'
    assert store.get_artifact(run_id, "crate/ro-crate-metadata.json") == b'{"@graph": []}'
    assert store.get_artifact(run_id, "crate/sub/file.bin") == bytes(range(256))
    assert store.get_artifact(run_id, "grounding.txt") is None
    assert store.get_artifact(NOWHERE, "spans.jsonl") is None
    with _raises(FileExistsError, "an artifact written twice"):
        store.put_artifact(run_id, "spans.jsonl", b"again")
    assert store.get_artifact(run_id, "spans.jsonl") == b'{"name": "invoke_agent"}\n'
    for name in MALFORMED_ARTIFACTS:
        assert store.get_artifact(run_id, name) is None, name
        with _raises(ValueError, f"the malformed artifact name {name!r}"):
            store.put_artifact(run_id, name, b"x")
    assert store.get(run_id) == envelope
    assert store.where(run_id)
    assert make("runs").get_artifact(run_id, "crate/sub/file.bin") == bytes(range(256))


def check_schemas_are_kept_by_digest(make: MakeRunStorage) -> None:
    store = make("runs")
    schema = ClassSchema.of(ProbeClaim)
    store.append(stored_envelope(), schemas=[schema])
    store.append(stored_envelope(), schemas=[schema])
    assert store.get_schema(schema.digest) == dict(schema.json_schema)
    assert store.get_schema("0" * 64) is None
    for malformed in ("", "../" + schema.digest, schema.digest.upper()):
        assert store.get_schema(malformed) is None


def check_prompts_are_kept_with_their_run_only(make: MakeRunStorage) -> None:
    store = make("runs")
    secret = "What the researcher wrote, which only readers of the run may see."
    prompts = {"a" * 64: {"messages": [{"role": "user", "content": secret}]}}
    envelope = stored_envelope()
    run_id = envelope["invocation_id"]
    store.append(envelope, {"input": {}}, prompts=prompts)
    assert store.get_prompts(run_id) == prompts
    assert secret not in str(store.get(run_id))
    assert secret not in str(list(store.iter_envelopes()))
    other = stored_envelope()
    store.append(other)
    assert store.get_prompts(other["invocation_id"]) == {}
    assert store.get_prompts(NOWHERE) == {}


def check_a_malformed_run_name_names_nothing(make: MakeRunStorage) -> None:
    store = make("runs")
    store.append(stored_envelope())
    for malformed in ("", "..", "../runs", "/etc", "a/b"):
        assert not store.has(malformed), malformed
        assert store.get(malformed) is None
        assert store.get_request(malformed) is None
        assert store.get_prompts(malformed) == {}
        assert store.get_artifact(malformed, "spans.jsonl") is None


RUN_STORAGE_CHECKS: dict[str, Callable[[MakeRunStorage], None]] = {
    "a run is written once": check_a_run_is_written_once,
    "envelopes come back in the order stored": check_envelopes_come_back_in_the_order_stored,
    "envelopes are found by conversation": check_envelopes_are_found_by_conversation,
    "artifacts are kept once beside their run": check_artifacts_are_kept_once_beside_their_run,
    "schemas are kept by digest": check_schemas_are_kept_by_digest,
    "prompts are kept with their run only": check_prompts_are_kept_with_their_run_only,
    "a malformed run name names nothing": check_a_malformed_run_name_names_nothing,
}


def check_run_storage(make: MakeRunStorage) -> None:
    """Every `RunStorage` check, each on stores of its own."""
    for n, check in enumerate(RUN_STORAGE_CHECKS.values()):
        check(_named(make, n))


# --- Projects ------------------------------------------------------------------------------------


def file_inventory(*paths: str) -> dict[str, Any]:
    """A `FileInventory` document listing `paths`."""
    return FileInventory(
        inventory_tool="dd-inventory",
        inventory_tool_version="0.1.0",
        inventory_made_at=datetime(2026, 10, 30, tzinfo=UTC),
        inventory_files=[
            InventoryFile(
                file_path=path,
                file_size=10,
                file_sha256="a" * 64,
                file_media_type="text/csv",
                file_pronom_ids=["x-fmt/18"],
                file_identified_by=IdentificationMethod.EXTENSION,
            )
            for path in paths
        ],
    ).model_dump(mode="json", exclude_none=True)


def drafted_readme() -> Envelope:
    """A succeeded run whose payload is a first draft of a README, from the document stub run
    through a conductor of its own."""
    return drafted(DocumentKind.README)


def drafted(kind: DocumentKind, *, asks: bool = False) -> Envelope:
    """A succeeded run whose payload is a first draft of a document of `kind`, from the document
    stub run through a conductor of its own. With `asks`, the draft asks `STUB_QUESTION`."""
    with tempfile.TemporaryDirectory(prefix="dd-storage-check-") as runs:
        conductor = make_conductor(Path(runs), DocumentStub(asks=asks))
        return conductor.invoke(
            request("stub.document", document_request(kind)), acting_for=TEST_PRINCIPAL
        )


def check_the_log_is_append_only_and_the_latest_inventory_wins(make: MakeProjectStorage) -> None:
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    assert store.exists(project_id)
    assert store.inventory(project_id) is None
    first, second = file_inventory("a.csv"), file_inventory("a.csv", "b.csv")
    digest = store.add_inventory(project_id, first, acted_for=TEST_PRINCIPAL, caused_by="check")
    assert digest == input_hash(first)
    before = store.events(project_id)
    store.add_inventory(project_id, second, acted_for=TEST_PRINCIPAL, caused_by="check")
    store.add_inventory(project_id, first, acted_for=TEST_PRINCIPAL, caused_by="check")
    after = store.events(project_id)
    assert after[: len(before)] == before
    assert [e["event"] for e in after] == [PROJECT_CREATED] + [INVENTORY_ADDED] * 3
    ids = [e["event_id"] for e in after]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    for event in after:
        assert event["project_id"] == project_id
        assert event["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id
        assert event["caused_by"] == "check"
    assert store.inventory(project_id) == first
    assert make("projects").events(project_id) == after


def check_a_refused_change_records_nothing(make: MakeProjectStorage) -> None:
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    absolute = file_inventory("data.csv")
    absolute["inventory_files"][0]["file_path"] = "/home/someone/data.csv"
    for document in ({"schema_class": "FileList", "files": []}, absolute):
        with _raises(ProjectError, "not a FileInventory"):
            store.add_inventory(project_id, document, acted_for=TEST_PRINCIPAL, caused_by="check")
    with _raises(ProjectError, "a title too long"):
        store.create(acted_for=TEST_PRINCIPAL, caused_by="check", title="x" * 10_000)
    assert [e["event"] for e in store.events(project_id)] == [PROJECT_CREATED]
    assert [s["project_id"] for s in store.projects()] == [project_id]


def check_an_unknown_project_is_refused(make: MakeProjectStorage) -> None:
    store = make("projects")
    for project_id in (NOWHERE, "../escape", "", "a/b"):
        assert not store.exists(project_id)
        with _raises(ProjectError, f"an inventory for {project_id!r}"):
            store.add_inventory(
                project_id, file_inventory(), acted_for=TEST_PRINCIPAL, caused_by="check"
            )
        with _raises(ProjectError, f"the events of {project_id!r}"):
            store.events(project_id)
        with _raises(UnknownProjectError, f"a conversation in {project_id!r}"):
            store.start_conversation(project_id, acted_for=TEST_PRINCIPAL, caused_by="check")
    assert store.projects() == []


def check_projects_are_listed_in_the_order_created(make: MakeProjectStorage) -> None:
    store = make("projects")
    first = store.create(acted_for=TEST_PRINCIPAL, caused_by="check", title="  First ")
    second = store.create(acted_for=TEST_PRINCIPAL, caused_by="check", title="   ")
    summaries = store.projects()
    assert [s["project_id"] for s in summaries] == [first, second]
    assert summaries[0]["title"] == "First" and summaries[1]["title"] is None
    assert store.summary(first) == summaries[0]


def check_a_conversation_is_found_after_a_restart(make: MakeProjectStorage) -> None:
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    other = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    conversation_id = store.start_conversation(
        project_id, acted_for=TEST_PRINCIPAL, caused_by="check"
    )
    assert store.project_of(conversation_id) == project_id
    started = store.events(project_id)[-1]
    assert started["event"] == CONVERSATION_STARTED
    assert started["conversation_id"] == conversation_id
    assert store.events(other)[-1]["event"] == PROJECT_CREATED

    again = make("projects")
    assert again.project_of(conversation_id) == project_id
    assert again.project_of(NOWHERE) is None
    later = again.start_conversation(other, acted_for=TEST_PRINCIPAL, caused_by="check")
    assert again.project_of(later) == other
    assert make("projects").project_of(later) == other


def check_a_stale_change_is_refused_and_recorded(make: MakeProjectStorage) -> None:
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    draft = drafted_readme()
    first = store.record_draft(project_id, draft)
    (document,) = store.documents(project_id)
    shown = document["versions"][-1]
    assert shown["text"] == draft.to_document()["payload"]["document_text"]
    assert shown["digest"] == text_digest(shown["text"])
    store.edit(
        project_id,
        first.document_id,
        1,
        shown["digest"],
        "# Newer\n",
        acted_for=TEST_PRINCIPAL,
        caused_by="check",
    )
    stale = Decision(first.document_id, 1, shown["digest"], APPROVED)
    with _raises(ChangeRefusedError, "a decision on a version no longer the latest"):
        store.decide(project_id, stale, acted_for=TEST_PRINCIPAL, caused_by="check")
    assert store.events(project_id)[-1]["event"] == DOCUMENT_CHANGE_REFUSED
    (document,) = make("projects").documents(project_id)
    assert [v["text"] for v in document["versions"]][-1] == "# Newer\n"
    assert [v["state"] for v in document["versions"]] == ["proposed", "proposed"]


def check_concurrent_decisions_on_one_version_admit_one(make: MakeProjectStorage) -> None:
    """Two people decide on the same version at once: the read-then-append is atomic for the
    project, so one decision is recorded and the other refused."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    ref = store.record_draft(project_id, drafted_readme())
    (document,) = store.documents(project_id)
    digest = document["versions"][-1]["digest"]
    decision = Decision(ref.document_id, ref.version, digest, APPROVED)
    deciders = 8
    start = threading.Barrier(deciders)
    outcomes: list[str] = []
    guard = threading.Lock()

    def decide() -> None:
        start.wait()
        try:
            store.decide(project_id, decision, acted_for=TEST_PRINCIPAL, caused_by="check")
            outcome = "decided"
        except ChangeRefusedError:
            outcome = "refused"
        with guard:
            outcomes.append(outcome)

    threads = [threading.Thread(target=decide) for _ in range(deciders)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(outcomes) == ["decided"] + ["refused"] * (deciders - 1), outcomes
    kinds = [e["event"] for e in store.events(project_id)]
    assert kinds.count(DOCUMENT_VERSION_DECIDED) == 1
    assert kinds.count(DOCUMENT_CHANGE_REFUSED) == deciders - 1
    (document,) = store.documents(project_id)
    assert document["versions"][-1]["state"] == APPROVED


def check_the_metadata_record_is_the_one_approved_last(make: MakeProjectStorage) -> None:
    """A drafter is given the metadata record a person approved last, and nothing a person has
    not approved: not a version proposed or rejected since, nor another kind of document."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")

    def decide(ref_kind: DocumentKind, verdict: Verdict, reason: str | None = None) -> str:
        ref = store.record_draft(project_id, drafted(ref_kind))
        latest = next(d for d in store.documents(project_id) if d["document_id"] == ref.document_id)
        digest = latest["versions"][-1]["digest"]
        decision = Decision(ref.document_id, ref.version, digest, verdict, reason)
        store.decide(project_id, decision, acted_for=TEST_PRINCIPAL, caused_by="check")
        return ref.document_id

    store.record_draft(project_id, drafted(DocumentKind.METADATA_RECORD))
    decide(DocumentKind.README, APPROVED)
    assert store.metadata_record(project_id) is None

    first = decide(DocumentKind.METADATA_RECORD, APPROVED)
    decide(DocumentKind.METADATA_RECORD, REJECTED, "Not this one.")
    store.record_draft(project_id, drafted(DocumentKind.METADATA_RECORD))
    decide(DocumentKind.README, APPROVED)
    record = make("projects").metadata_record(project_id)
    assert record is not None
    assert record["version_ref"] == {"document_id": first, "version": 1}
    (approved,) = [d for d in store.documents(project_id) if d["document_id"] == first]
    assert record["document_text"] == approved["versions"][0]["text"]
    assert record["media_type"] == approved["versions"][0]["media_type"]
    assert (
        ClassSchema.of(DraftRequest).errors(
            {"schema_class": "DraftRequest", "document_kind": "readme", "metadata_record": record}
        )
        == []
    )

    second = decide(DocumentKind.METADATA_RECORD, APPROVED)
    record = store.metadata_record(project_id)
    assert record is not None
    assert record["version_ref"] == {"document_id": second, "version": 1}


def check_a_report_and_a_package_are_kept_by_digest(make: MakeProjectStorage) -> None:
    """A validation report and a deposit package are kept by digest and named in the log
    (docs/specs/deposit.md, invariants 8 and 9); a package the log does not name is not found."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    report = {"@type": "sh:ValidationReport", "sh:conforms": True}
    report_digest = store.record_validation(
        project_id,
        report,
        conforms=True,
        requirements_digest=None,
        acted_for=TEST_PRINCIPAL,
        caused_by="check",
    )
    assert report_digest == input_hash(report)
    package = b"PK\x05\x06" + bytes(18)
    digest = store.record_package(
        project_id,
        package,
        about={"report_digest": report_digest, "event": "not this"},
        acted_for=TEST_PRINCIPAL,
        caused_by="check",
    )
    assert digest == hashlib.sha256(package).hexdigest()
    validated, built = make("projects").events(project_id)[-2:]
    assert (validated["event"], validated["digest"]) == (PROJECT_VALIDATED, report_digest)
    assert validated["conforms"] is True
    assert (built["event"], built["digest"]) == (PACKAGE_BUILT, digest)
    assert built["report_digest"] == report_digest
    assert make("projects").package(project_id, digest) == package
    assert store.package(project_id, "0" * 64) is None
    with _raises(UnknownProjectError, "a package of an unknown project"):
        store.record_package(
            NOWHERE, package, about={}, acted_for=TEST_PRINCIPAL, caused_by="check"
        )


def check_answers_stand_until_answered_again(make: MakeProjectStorage) -> None:
    """A person answers the latest version's questions. An answer to another version, or to a
    question it does not ask, is refused and recorded; a malformed one records nothing. The
    latest answer to a question stands across versions and documents, and only for its kind."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    asked = STUB_QUESTION.question_id
    assert store.answers(project_id, DocumentKind.README) is None
    ref = store.record_draft(project_id, drafted(DocumentKind.README, asks=True))

    def answer(text: str, version: int = 1, question: str = asked) -> None:
        given = [DraftAnswer(answered_question=question, answer_text=text)]
        store.answer(
            project_id, ref.document_id, version, given, acted_for=TEST_PRINCIPAL, caused_by="check"
        )

    for malformed in ("   ", "x" * 10_000):
        with _raises(ProjectError, f"the answer {malformed[:5]!r}"):
            answer(malformed)
    twice = [DraftAnswer(answered_question=asked, answer_text="a")] * 2
    with _raises(ProjectError, "a question answered twice"):
        store.answer(
            project_id, ref.document_id, 1, twice, acted_for=TEST_PRINCIPAL, caused_by="check"
        )
    assert [e["event"] for e in store.events(project_id)][-1] != DOCUMENT_CHANGE_REFUSED

    for version, question, refusal in (
        (2, asked, Refusal.NOT_LATEST),
        (1, "q-" + "1" * 16, Refusal.NOT_ASKED),
    ):
        try:
            answer("Soil", version, question)
        except ChangeRefusedError as refused:
            assert refused.refusal == refusal
        else:
            raise AssertionError(f"an answer refused as {refusal} was recorded")
        assert store.events(project_id)[-1]["event"] == DOCUMENT_CHANGE_REFUSED

    answer("  Soil cores  ")
    answer("Soil cores from two fields")
    answered = store.events(project_id)[-1]
    assert answered["event"] == DOCUMENT_QUESTION_ANSWERED
    assert answered["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id
    expected = [{"answered_question": asked, "answer_text": "Soil cores from two fields"}]
    assert make("projects").answers(project_id, DocumentKind.README) == expected
    (document,) = store.documents(project_id)
    assert [(a["question_id"], a["version"]) for a in document["answers"]] == [(asked, 1)]
    assert store.answers(project_id, DocumentKind.DATA_DICTIONARY) is None

    # A person's edit asks nothing, but the answers still stand for the next draft.
    (document,) = store.documents(project_id)
    store.edit(
        project_id,
        ref.document_id,
        1,
        document["versions"][-1]["digest"],
        "# Edited\n",
        acted_for=TEST_PRINCIPAL,
        caused_by="check",
    )
    assert store.answers(project_id, DocumentKind.README) == expected

    # A redraft is a document of its own until it names the version it revises: the answers
    # outlive the document they were given to, and the latest answer to a question stands.
    newer = store.record_draft(project_id, drafted(DocumentKind.README, asks=True))
    assert store.answers(project_id, DocumentKind.README) == expected
    given = [DraftAnswer(answered_question=asked, answer_text="Topsoil cores")]
    store.answer(
        project_id, newer.document_id, 1, given, acted_for=TEST_PRINCIPAL, caused_by="check"
    )
    latest = [{"answered_question": asked, "answer_text": "Topsoil cores"}]
    assert store.answers(project_id, DocumentKind.README) == latest


PROJECT_STORAGE_CHECKS: dict[str, Callable[[MakeProjectStorage], None]] = {
    "the log is append-only and the latest inventory wins": (
        check_the_log_is_append_only_and_the_latest_inventory_wins
    ),
    "a refused change records nothing": check_a_refused_change_records_nothing,
    "an unknown project is refused": check_an_unknown_project_is_refused,
    "projects are listed in the order created": check_projects_are_listed_in_the_order_created,
    "a conversation is found after a restart": check_a_conversation_is_found_after_a_restart,
    "a stale change is refused and recorded": check_a_stale_change_is_refused_and_recorded,
    "concurrent decisions on one version admit one": (
        check_concurrent_decisions_on_one_version_admit_one
    ),
    "the metadata record is the one approved last": (
        check_the_metadata_record_is_the_one_approved_last
    ),
    "a report and a package are kept by digest": check_a_report_and_a_package_are_kept_by_digest,
    "answers stand until answered again": check_answers_stand_until_answered_again,
}


def check_project_storage(make: MakeProjectStorage) -> None:
    """Every `ProjectStorage` check, each on stores of its own."""
    for n, check in enumerate(PROJECT_STORAGE_CHECKS.values()):
        check(_named(make, n))

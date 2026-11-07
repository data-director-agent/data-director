"""Project documents, their versions and a person's decision on each (docs/specs/projects.md,
invariants 9 to 15): the harness decides and records, and the log is the audit trail."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dd_harness.projects import (
    APPROVED,
    DOCUMENT_CHANGE_REFUSED,
    DOCUMENT_VERSION_ADDED,
    DOCUMENT_VERSION_DECIDED,
    PROPOSED,
    REASON_MAX_LENGTH,
    REJECTED,
    ChangeRefusedError,
    Decision,
    ProjectError,
    ProjectStore,
    Refusal,
    UnknownProjectError,
    text_digest,
)
from dd_harness.testing import (
    TEST_PRINCIPAL,
    DocumentStub,
    document_request,
    make_conductor,
    request,
)
from dd_sdk.contract.models import DocumentKind, DocumentVersionRef, Envelope, Principal

DECIDER = Principal(principal_id="https://orcid.org/0000-0002-1825-0097", name="Josiah Carberry")


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def draft(runs_dir: Path) -> Envelope:
    """A succeeded run whose payload is a first draft of a README."""
    conductor = make_conductor(runs_dir, DocumentStub())
    return conductor.invoke(
        request("stub.document", document_request(DocumentKind.README)), acting_for=TEST_PRINCIPAL
    )


@pytest.fixture
def project(store: ProjectStore) -> str:
    return store.create(acted_for=TEST_PRINCIPAL, caused_by="test")


def latest(store: ProjectStore, project_id: str) -> dict[str, Any]:
    (document,) = store.documents(project_id)
    version: dict[str, Any] = document["versions"][-1]
    return version


def decide(store: ProjectStore, project_id: str, **given: Any) -> DocumentVersionRef:
    shown = latest(store, project_id)
    fields = {
        "document_id": shown["document_id"],
        "version": shown["version"],
        "digest": text_digest(shown["text"]),
        **given,
    }
    return store.decide(project_id, Decision(**fields), acted_for=DECIDER, caused_by="test")


def test_a_draft_becomes_the_first_proposed_version_and_names_its_run(
    store: ProjectStore, project: str, draft: Envelope
) -> None:
    ref = store.record_draft(project, draft)
    assert ref.version == 1
    (document,) = store.documents(project)
    assert document["document_id"] == ref.document_id
    assert document["document_kind"] == "readme"
    (version,) = document["versions"]
    assert version["state"] == PROPOSED and version["decision"] is None
    assert version["text"] == draft.to_document()["payload"]["document_text"]
    assert version["digest"] == text_digest(version["text"])
    assert version["drafted_by"]["invocation_id"] == draft.invocation_id
    assert version["drafted_by"]["agent_id"] == "stub.document"
    assert version["added_by"]["principal_id"] == TEST_PRINCIPAL.principal_id
    event = store.events(project)[-1]
    assert event["event"] == DOCUMENT_VERSION_ADDED
    assert event["caused_by"] == draft.invocation_id  # an event caused by a run names it


def test_only_a_succeeded_document_becomes_a_version(
    store: ProjectStore, project: str, draft: Envelope
) -> None:
    failed = draft.model_copy(
        update={"outcome": draft.outcome.model_copy(update={"status": "failed"})}
    )
    with pytest.raises(ProjectError, match="did not succeed"):
        store.record_draft(project, failed)
    with pytest.raises(ProjectError, match="no Document"):
        store.record_draft(project, draft.model_copy(update={"payload": None}))
    assert store.documents(project) == []


@pytest.mark.requirement("C13.3")
def test_a_plain_approval_needs_no_reason_and_is_final(
    store: ProjectStore, project: str, draft: Envelope
) -> None:
    store.record_draft(project, draft)
    ref = decide(store, project, verdict=APPROVED)
    version = latest(store, project)
    assert (ref.version, version["state"]) == (1, APPROVED)
    assert version["decision"]["reason"] is None
    assert version["decision"]["decided_by"]["principal_id"] == DECIDER.principal_id

    decided = store.events(project)[-1]
    assert decided["event"] == DOCUMENT_VERSION_DECIDED
    assert decided["digest"] == version["digest"]
    assert decided["acted_for"]["principal_id"] == DECIDER.principal_id

    # Decided once, for good: deciding again is refused, recorded, and changes nothing.
    with pytest.raises(ChangeRefusedError) as refused:
        decide(store, project, verdict=REJECTED, reason="Changed my mind.")
    assert refused.value.refusal is Refusal.DECIDED
    assert latest(store, project)["state"] == APPROVED
    assert store.events(project)[-1]["event"] == DOCUMENT_CHANGE_REFUSED


@pytest.mark.requirement("C13.3")
@pytest.mark.parametrize(
    ("given", "message"),
    [
        ({"verdict": REJECTED}, "rejecting needs a reason"),
        ({"verdict": REJECTED, "reason": "   "}, "rejecting needs a reason"),
        ({"verdict": APPROVED, "edited_text": "# Edited\n"}, "approving an edit needs a reason"),
        (
            {"verdict": REJECTED, "reason": "No.", "edited_text": "# Edited\n"},
            "can be approved, not rejected",
        ),
        ({"verdict": APPROVED, "reason": "x" * (REASON_MAX_LENGTH + 1)}, "at most"),
        ({"verdict": "maybe"}, "not 'maybe'"),
        # A name no document could have is malformed, so even its refusal is not recorded.
        ({"verdict": APPROVED, "document_id": "x" * 10_000}, "UUIDv7"),
        ({"verdict": APPROVED, "digest": "not-a-digest"}, "SHA-256"),
    ],
)
def test_a_malformed_decision_is_refused_and_records_nothing(
    store: ProjectStore, project: str, draft: Envelope, given: dict[str, Any], message: str
) -> None:
    store.record_draft(project, draft)
    before = store.events(project)
    with pytest.raises(ProjectError, match=message):
        decide(store, project, **given)
    assert store.events(project) == before


@pytest.mark.requirement("C13.3")
def test_a_rejection_keeps_its_reason(store: ProjectStore, project: str, draft: Envelope) -> None:
    store.record_draft(project, draft)
    decide(store, project, verdict=REJECTED, reason="  The title is wrong.  ")
    version = latest(store, project)
    assert version["state"] == REJECTED
    assert version["decision"]["reason"] == "The title is wrong."


@pytest.mark.requirement("C13.3")
def test_editing_then_approving_writes_the_edit_and_its_approval_together(
    store: ProjectStore, project: str, draft: Envelope
) -> None:
    first = store.record_draft(project, draft)
    before = len(store.events(project))
    ref = decide(store, project, verdict=APPROVED, reason="Named the site.", edited_text="# Soil\n")
    assert ref == DocumentVersionRef(document_id=first.document_id, version=2)

    added, decided = store.events(project)[before:]
    assert (added["event"], decided["event"]) == (DOCUMENT_VERSION_ADDED, DOCUMENT_VERSION_DECIDED)
    assert added["caused_by"] == decided["caused_by"] == "test"
    assert decided["version"] == 2 and decided["digest"] == text_digest("# Soil\n")

    edited_from, edited = store.documents(project)[0]["versions"]
    assert edited_from["state"] == PROPOSED  # the version edited from keeps its own state
    assert edited["state"] == APPROVED and edited["decision"]["reason"] == "Named the site."
    assert edited["text"] == "# Soil\n"
    assert edited["revises"] == {"document_id": first.document_id, "version": 1}
    assert edited["drafted_by"] is None  # a person's version names no run
    assert edited["added_by"]["principal_id"] == DECIDER.principal_id
    assert edited["media_type"] == edited_from["media_type"]


def test_an_edit_that_changes_nothing_is_refused(
    store: ProjectStore, project: str, draft: Envelope
) -> None:
    store.record_draft(project, draft)
    with pytest.raises(ProjectError, match="the same"):
        decide(
            store, project, verdict=APPROVED, reason="x", edited_text=latest(store, project)["text"]
        )
    assert len(store.documents(project)[0]["versions"]) == 1


def test_a_person_may_edit_without_approving(
    store: ProjectStore, project: str, draft: Envelope
) -> None:
    first = store.record_draft(project, draft)
    shown = latest(store, project)
    ref = store.edit(
        project,
        first.document_id,
        1,
        shown["digest"],
        "# Edited\n",
        acted_for=DECIDER,
        caused_by="test",
    )
    assert ref.version == 2
    assert [v["state"] for v in store.documents(project)[0]["versions"]] == [PROPOSED, PROPOSED]


@pytest.mark.requirement("C13.3")
def test_a_decision_on_a_stale_version_is_refused_and_recorded(
    store: ProjectStore, project: str, draft: Envelope
) -> None:
    first = store.record_draft(project, draft)
    stale = latest(store, project)
    # A newer version, here a person's edit, replaces the one the stale screen shows.
    store.edit(
        project,
        first.document_id,
        1,
        stale["digest"],
        "# Newer\n",
        acted_for=DECIDER,
        caused_by="t",
    )
    with pytest.raises(ChangeRefusedError) as refused:
        store.decide(
            project,
            Decision(first.document_id, 1, stale["digest"], APPROVED),
            acted_for=DECIDER,
            caused_by="test",
        )
    assert refused.value.refusal is Refusal.NOT_LATEST
    assert "version 2" in refused.value.detail
    recorded = store.events(project)[-1]
    assert recorded["event"] == DOCUMENT_CHANGE_REFUSED
    assert recorded["refusal"] == "version-not-latest" and recorded["latest_version"] == 2
    assert [v["state"] for v in store.documents(project)[0]["versions"]] == [PROPOSED, PROPOSED]


def test_a_decision_on_other_text_or_another_document_is_refused(
    store: ProjectStore, project: str, draft: Envelope
) -> None:
    first = store.record_draft(project, draft)
    for decision, refusal in [
        (Decision(first.document_id, 1, "0" * 64, APPROVED), Refusal.DIGEST),
        (
            Decision("0192f3a4-0000-7000-8000-000000000000", 1, "0" * 64, APPROVED),
            Refusal.NO_DOCUMENT,
        ),
    ]:
        with pytest.raises(ChangeRefusedError) as refused:
            store.decide(project, decision, acted_for=DECIDER, caused_by="test")
        assert refused.value.refusal is refusal
        assert store.events(project)[-1]["refusal"] == refusal.value
    assert latest(store, project)["state"] == PROPOSED


def test_a_document_of_another_project_is_not_in_this_one(
    store: ProjectStore, project: str, draft: Envelope
) -> None:
    first = store.record_draft(project, draft)
    other = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    digest = latest(store, project)["digest"]
    with pytest.raises(ChangeRefusedError) as refused:
        store.decide(
            other,
            Decision(first.document_id, 1, digest, APPROVED),
            acted_for=DECIDER,
            caused_by="t",
        )
    assert refused.value.refusal is Refusal.NO_DOCUMENT
    with pytest.raises(UnknownProjectError):
        store.documents("0192f3a4-0000-7000-8000-000000000000")


def test_a_regeneration_is_the_next_version_of_the_document_it_revises(
    store: ProjectStore, project: str, draft: Envelope, runs_dir: Path
) -> None:
    first = store.record_draft(project, draft)
    decide(store, project, verdict=REJECTED, reason="Too short.")
    payload = {**draft.to_document()["payload"], "revises": first.model_dump(mode="json")}
    regenerated = draft.model_copy(update={"payload": payload})
    regenerated = Envelope.model_validate(regenerated.to_document())
    ref = store.record_draft(project, regenerated)
    assert ref == DocumentVersionRef(document_id=first.document_id, version=2)
    assert [v["state"] for v in store.documents(project)[0]["versions"]] == [REJECTED, PROPOSED]

    unknown = DocumentVersionRef(document_id=first.document_id, version=9).model_dump(mode="json")
    elsewhere = Envelope.model_validate(
        {**draft.to_document(), "payload": {**payload, "revises": unknown}}
    )
    with pytest.raises(ProjectError, match="revises no version"):
        store.record_draft(project, elsewhere)


def test_a_revision_of_another_kind_is_refused_and_records_nothing(
    store: ProjectStore, project: str, draft: Envelope
) -> None:
    first = store.record_draft(project, draft)
    before = store.events(project)
    payload = {
        **draft.to_document()["payload"],
        "document_kind": DocumentKind.DMP.value,
        "revises": first.model_dump(mode="json"),
    }
    other_kind = Envelope.model_validate({**draft.to_document(), "payload": payload})
    with pytest.raises(ProjectError, match="revises a readme with a dmp"):
        store.record_draft(project, other_kind)
    assert store.events(project) == before


def test_a_malformed_edit_records_nothing(
    store: ProjectStore, project: str, draft: Envelope
) -> None:
    store.record_draft(project, draft)
    before = store.events(project)
    with pytest.raises(ProjectError, match="UUIDv7"):
        store.edit(project, "../x", 1, "0" * 64, "# New\n", acted_for=DECIDER, caused_by="t")
    assert store.events(project) == before


def test_the_current_version_is_the_latest_of_the_document_with_its_decision(
    store: ProjectStore, project: str, draft: Envelope
) -> None:
    assert store.current_version(project, DocumentKind.README) is None
    payload = {**draft.to_document()["payload"], "document_title": "About the soil cores"}
    titled = Envelope.model_validate({**draft.to_document(), "payload": payload})
    first = store.record_draft(project, titled)
    decide(store, project, verdict=REJECTED, reason="Too short.")

    given = store.current_version(project, DocumentKind.README)

    assert given == {
        "version_ref": first.model_dump(mode="json"),
        "document_title": "About the soil cores",
        "media_type": latest(store, project)["media_type"],
        "document_text": latest(store, project)["text"],
        "version_state": REJECTED,
        "decision_reason": "Too short.",
    }
    assert store.current_version(project, DocumentKind.README, first.document_id) == given
    assert store.current_version(project, DocumentKind.DATA_DICTIONARY) is None
    with pytest.raises(ProjectError, match="is a readme, not a data_dictionary"):
        store.current_version(project, DocumentKind.DATA_DICTIONARY, first.document_id)
    with pytest.raises(ProjectError, match="has no document"):
        store.current_version(project, DocumentKind.README, "0" * 8 + first.document_id[8:])

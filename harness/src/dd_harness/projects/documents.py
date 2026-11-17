"""A project's documents: drafts, a person's edits and decisions, answers to a draft's questions,
and what is read from them (docs/specs/projects.md, docs/specs/drafting.md).

A document is a sequence of versions (`dd_harness.projects.fold`). An agent drafts a version
(`record_draft`, from a succeeded run's `Document` payload) or a person edits one (`edit`). A
person's decision is a `document_version_decided` event (`decide`): every version begins
`proposed`, and one decision makes it `approved` or `rejected` for good. A decision or edit that
names anything but the document's latest text, or a version already decided, is refused, and the
refusal is a `document_change_refused` event. `documents` folds the log into each document and
the state of each of its versions, which is what the app shows.

A version may ask the researcher questions (`DocumentQuestion`, docs/specs/drafting.md). A
person's answer is a `document_question_answered` event (`answer`), given to a question of the
document's latest version. Question identifiers are derived from the gap a question fills, so
an answer stands until the person answers the same question again. `answers` gives the latest
answer to each question of the documents of a kind, which the conductor puts into the next
`DraftRequest`.

Giving a drafter the version it regenerates is TODO(#394).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dd_harness.projects.decisions import Decision, check_answers, check_names
from dd_harness.projects.fold import APPROVED, check_latest, fold, text_digest
from dd_harness.projects.rules import (
    DOCUMENT_QUESTION_ANSWERED,
    DOCUMENT_VERSION_ADDED,
    DOCUMENT_VERSION_DECIDED,
    PROJECT_ID,
    ProjectError,
    ProjectRules,
    Refusal,
    Refused,
)
from dd_sdk.contract.models import (
    Document,
    DocumentKind,
    DocumentVersionRef,
    DraftAnswer,
    Envelope,
    OutcomeStatus,
    Principal,
    new_invocation_id,
)

if TYPE_CHECKING:
    from dd_harness.storage import ProjectSection


class Documents(ProjectRules):
    """The rules of a project's documents and their versions."""

    def record_draft(self, project_id: str, envelope: Envelope) -> DocumentVersionRef:
        """Record a run's `Document` payload as a proposed version (docs/specs/projects.md,
        invariants 9 and 10): the first version of a new document if it revises nothing, else the
        next version of the document it revises. The event names the run and acts for whom the
        run acted for.

        Raises `ProjectError` for a run that did not succeed, a payload of another class, or a
        `revises` that names no version of this project. Nothing is recorded."""
        if envelope.outcome.status != OutcomeStatus.SUCCEEDED:
            raise ProjectError(f"run {envelope.invocation_id} did not succeed")
        payload = envelope.payload
        if payload is None or payload.model_dump().get("schema_class") != "Document":
            raise ProjectError(f"run {envelope.invocation_id} returned no Document")
        document = envelope.payload_as(Document)
        # A run already going when the project was deleted finishes and is recorded
        # (docs/specs/projects.md, invariant 24).
        with self._section(project_id, allow_deleted=True) as section:
            document_id, version = _next_version(fold(section.events()), document, envelope)
            detail = self._version(
                project_id,
                document_id,
                version,
                document.document_text,
                {
                    "document_kind": document.document_kind.value,
                    "document_title": document.document_title,
                    "media_type": document.media_type,
                    "conforms_to": document.conforms_to,
                    "revises": document.revises.model_dump(mode="json")
                    if document.revises
                    else None,
                    "drafted_by": {
                        "agent_id": envelope.agent_id,
                        "agent_version": envelope.agent_version,
                        "invocation_id": envelope.invocation_id,
                        "document_derivation": document.document_derivation.value,
                    },
                    "questions": [
                        q.model_dump(mode="json", exclude_none=True)
                        for q in document.document_questions
                    ]
                    or None,
                },
            )
            section.append(
                [
                    self._event(
                        project_id,
                        DOCUMENT_VERSION_ADDED,
                        envelope.acting_for,
                        envelope.invocation_id,
                        detail,
                    )
                ]
            )
        return DocumentVersionRef(document_id=document_id, version=version)

    def edit(
        self,
        project_id: str,
        document_id: str,
        version: int,
        digest: str,
        text: str,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> DocumentVersionRef:
        """Record a person's edit of the latest version as a new proposed version. `digest` is
        the digest of the text they edited (docs/specs/projects.md, invariant 12).

        Raises `ChangeRefusedError`, and records the refusal, if the version is not the latest or
        the digest is not its; `ProjectError`, which records nothing, if the text is unchanged
        or the document or digest is malformed."""
        check_names(document_id, digest)

        def change(section: ProjectSection) -> DocumentVersionRef | Refused:
            parent = check_latest(section.events(), document_id, version, digest, deciding=False)
            if isinstance(parent, Refused):
                return parent
            detail = self._edited(project_id, parent, text)
            section.append(
                [self._event(project_id, DOCUMENT_VERSION_ADDED, acted_for, caused_by, detail)]
            )
            return DocumentVersionRef(document_id=document_id, version=detail["version"])

        return self._checked(project_id, acted_for, caused_by, change)

    def decide(
        self, project_id: str, decision: Decision, *, acted_for: Principal, caused_by: str
    ) -> DocumentVersionRef:
        """Record the decision `acted_for` made on the latest version (docs/specs/projects.md,
        invariants 11 to 15). With an edited text, the person's version and its approval are
        written together, or neither is. Returns the version decided.

        Raises `ProjectError` for a decision malformed in itself, which records nothing, and
        `ChangeRefusedError` for one on any text but the undecided latest, which records the
        refusal."""
        decision.check()

        def change(section: ProjectSection) -> DocumentVersionRef | Refused:
            decided = check_latest(
                section.events(),
                decision.document_id,
                decision.version,
                decision.digest,
                deciding=True,
            )
            if isinstance(decided, Refused):
                return decided
            events = []
            if decision.edited_text is not None:
                decided = self._edited(project_id, decided, decision.edited_text)
                events.append(
                    self._event(project_id, DOCUMENT_VERSION_ADDED, acted_for, caused_by, decided)
                )
            reason = decision.stated_reason
            outcome = {
                "document_id": decided["document_id"],
                "version": decided["version"],
                "digest": decided["digest"],
                "decision": decision.verdict,
                **({"reason": reason} if reason else {}),
            }
            events.append(
                self._event(project_id, DOCUMENT_VERSION_DECIDED, acted_for, caused_by, outcome)
            )
            section.append(events)
            return DocumentVersionRef(
                document_id=decided["document_id"], version=decided["version"]
            )

        return self._checked(project_id, acted_for, caused_by, change)

    def answer(
        self,
        project_id: str,
        document_id: str,
        version: int,
        answers: list[DraftAnswer],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> DocumentVersionRef:
        """Record `acted_for`'s answers to questions the latest version asks
        (docs/specs/drafting.md, invariant 6), one `document_question_answered` event each,
        written together. A decided version's questions may still be answered: the answers go
        into the next draft. Returns the version answered.

        Raises `ProjectError` for answers malformed in themselves, which records nothing, and
        `ChangeRefusedError` for answers to any version but the latest or to a question it does
        not ask, which records the refusal."""
        answers = check_answers(answers)
        if not PROJECT_ID.fullmatch(document_id):
            raise ProjectError("a document is named by its UUIDv7")

        def change(section: ProjectSection) -> DocumentVersionRef | Refused:
            latest = check_latest(section.events(), document_id, version, None, deciding=False)
            if isinstance(latest, Refused):
                return latest
            asked = {q["question_id"] for q in latest["questions"]}
            unasked = [a.answered_question for a in answers if a.answered_question not in asked]
            if unasked:
                return Refused(
                    Refusal.NOT_ASKED,
                    f"Version {version} does not ask {', '.join(unasked)}.",
                    {"document_id": document_id, "version": version, "questions": unasked},
                )
            section.append(
                [
                    self._event(
                        project_id,
                        DOCUMENT_QUESTION_ANSWERED,
                        acted_for,
                        caused_by,
                        {
                            "document_id": document_id,
                            "version": version,
                            "question_id": a.answered_question,
                            "answer_text": a.answer_text,
                        },
                    )
                    for a in answers
                ],
            )
            return DocumentVersionRef(document_id=document_id, version=version)

        return self._checked(project_id, acted_for, caused_by, change)

    def answers(self, project_id: str, document_kind: DocumentKind) -> list[dict[str, Any]] | None:
        """The answers a drafter of `document_kind` is given, as `DraftAnswer`s: the latest answer
        recorded to each question of any document of that kind, in the order last answered. None
        if there are none.

        A question's identifier is derived from the gap it fills, so it is the same in every
        draft of that kind. A redraft is its document's next version, but a project drafted
        before that may hold two documents of one kind, so an answer outlives the document it
        was given to."""
        kinds: dict[str, str] = {}
        latest: dict[str, str] = {}
        for event in self.events(project_id):
            if event["event"] == DOCUMENT_VERSION_ADDED:
                kinds[event["document_id"]] = event["document_kind"]
            elif (
                event["event"] == DOCUMENT_QUESTION_ANSWERED
                and kinds.get(event["document_id"]) == document_kind.value
            ):
                latest.pop(event["question_id"], None)
                latest[event["question_id"]] = event["answer_text"]
        given = [{"answered_question": q, "answer_text": text} for q, text in latest.items()]
        return given or None

    def documents(self, project_id: str) -> list[dict[str, Any]]:
        """Each document of the project, in the order first drafted, with every version oldest
        first: its text, who or what produced it, and its state as the log records it. Raises
        `UnknownProjectError` for an unknown project."""
        found = list(fold(self.events(project_id)).values())
        for document in found:
            for version in document["versions"]:
                version["text"] = self._text(project_id, version["digest"])
        return found

    def current_version(
        self, project_id: str, document_kind: DocumentKind, document_id: str | None = None
    ) -> dict[str, Any] | None:
        """The version a drafter of `document_kind` regenerates, as a `CurrentVersion`: the latest
        version of `document_id`, or, without one, of the project's document of that kind drafted
        or revised last. Its text, its state, and the reason a person gave for any decision on it.
        None if the project holds no document of the kind.

        Raises `ProjectError` if `document_id` names no document of this project, or one of
        another kind, and `UnknownProjectError` for an unknown project."""
        events = self.events(project_id)
        chosen = _chosen(fold(events), events, document_kind, document_id)
        if chosen is None:
            return None
        latest: dict[str, Any] = chosen["versions"][-1]
        given: dict[str, Any] = {
            "version_ref": {"document_id": chosen["document_id"], "version": latest["version"]},
            "media_type": latest["media_type"],
            "document_text": self._text(project_id, latest["digest"]),
            "version_state": latest["state"],
        }
        if latest["document_title"] is not None:
            given["document_title"] = latest["document_title"]
        if latest["decision"] is not None and latest["decision"]["reason"] is not None:
            given["decision_reason"] = latest["decision"]["reason"]
        return given

    def metadata_record(self, project_id: str) -> dict[str, Any] | None:
        """The metadata record a person approved last, as an `ApprovedMetadataRecord`: the
        version named by the last approval in the log of any `metadata_record` document. None if
        no version of one has been approved. A later version proposed or rejected does not
        displace it."""
        events = self.events(project_id)
        documents = fold(events)
        for event in reversed(events):
            if event["event"] != DOCUMENT_VERSION_DECIDED or event["decision"] != APPROVED:
                continue
            document = documents[event["document_id"]]
            if document["document_kind"] != DocumentKind.METADATA_RECORD.value:
                continue
            version = document["versions"][event["version"] - 1]
            record: dict[str, Any] = {
                "version_ref": {"document_id": event["document_id"], "version": event["version"]},
                "media_type": version["media_type"],
                "document_text": self._text(project_id, version["digest"]),
            }
            if version["conforms_to"] is not None:
                record["conforms_to"] = version["conforms_to"]
            return record
        return None

    def _text(self, project_id: str, digest: str) -> str:
        return self._blob(project_id, digest).decode("utf-8")

    def _edited(self, project_id: str, parent: dict[str, Any], text: str) -> dict[str, Any]:
        """The detail of a person's version after `parent`, its text kept. It names no run."""
        if text_digest(text) == parent["digest"]:
            raise ProjectError("the edited text is the same as the version edited")
        about = {
            key: parent[key]
            for key in ("document_kind", "document_title", "media_type", "conforms_to")
        }
        revises = {"document_id": parent["document_id"], "version": parent["version"]}
        return self._version(
            project_id,
            parent["document_id"],
            parent["version"] + 1,
            text,
            {**about, "revises": revises},
        )

    def _version(
        self,
        project_id: str,
        document_id: str,
        version: int,
        text: str,
        about: dict[str, Any],
    ) -> dict[str, Any]:
        """Keep a version's text, and return the detail of its `document_version_added` event."""
        digest = text_digest(text)
        self._keep_blob(project_id, digest, text.encode("utf-8"))
        return {
            "document_id": document_id,
            "version": version,
            "digest": digest,
            **{key: value for key, value in about.items() if value is not None},
        }


def _next_version(
    documents: dict[str, dict[str, Any]], document: Document, envelope: Envelope
) -> tuple[str, int]:
    """The document and version a drafted `document` becomes: version 1 of a new document if it
    revises nothing, else the next version of the one it revises. Raises `ProjectError` for a
    `revises` that names no version of the project, or one of another kind."""
    if document.revises is None:
        return new_invocation_id(), 1
    revised = documents.get(document.revises.document_id)
    if revised is None or document.revises.version > len(revised["versions"]):
        raise ProjectError(f"run {envelope.invocation_id} revises no version of this project")
    if document.document_kind.value != revised["document_kind"]:
        raise ProjectError(
            f"run {envelope.invocation_id} revises a {revised['document_kind']} "
            f"with a {document.document_kind.value}"
        )
    return revised["document_id"], len(revised["versions"]) + 1


def _chosen(
    documents: dict[str, dict[str, Any]],
    events: list[dict[str, Any]],
    document_kind: DocumentKind,
    document_id: str | None,
) -> dict[str, Any] | None:
    """The document `current_version` reads: `document_id`, checked to be of `document_kind`,
    or without one the document of that kind drafted or revised last, or None."""
    if document_id is not None:
        named = documents.get(document_id)
        if named is None:
            raise ProjectError(f"this project has no document {document_id!r}")
        if named["document_kind"] != document_kind.value:
            raise ProjectError(
                f"document {document_id!r} is a {named['document_kind']}, "
                f"not a {document_kind.value}"
            )
        return named
    # The last version added of the kind names the document drafted or revised last.
    chosen = None
    for event in events:
        if event["event"] != DOCUMENT_VERSION_ADDED:
            continue
        if event["document_kind"] == document_kind.value:
            chosen = documents[event["document_id"]]
    return chosen

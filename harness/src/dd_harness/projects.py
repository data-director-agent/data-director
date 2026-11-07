"""The project record: an append-only log of what changed in a project (docs/specs/projects.md).

A project is a record of its own that outlives any conversation. The harness keeps it under
`DD_PROJECTS_DIR`:

    <project_id>/events.jsonl                one event per line, in the order they happened
    <project_id>/blobs/sha256/<digest>       content an event added, kept once by digest

An event is never changed or removed. Each names whom it acted for and what caused it: the run
or request, or the command a person ran. The run store is separate: conversations are still
derived from it (docs/specs/orchestration.md), and the project is not.

What a project holds of its research data is a `FileInventory`, never the files. An inventory is
checked against the core class schema before it is added, and kept as its `dd-input-json-v1`
canonical bytes, so its digest is the input hash the conductor records when an agent is given it.

The repository a researcher chose is a `repository_chosen` event. It records each requirement
set the choice resolved to by reference and digest, and keeps the merged set as a blob, so that a
drafter and validation read exactly what was chosen (docs/specs/deposit.md). The last choice counts.

A document is a sequence of versions, each a `document_version_added` event whose text is kept as
a blob under the SHA-256 of its UTF-8 bytes. An agent drafts a version (`record_draft`, from a
succeeded run's `Document` payload) or a person edits one (`edit`). A person's decision is a
`document_version_decided` event (`decide`): every version begins `proposed`, and one decision
makes it `approved` or `rejected` for good. A decision or edit that names anything but the
document's latest text, or a version already decided, is refused, and the refusal is a
`document_change_refused` event. `documents` folds the log into each document and the state of
each of its versions, which is what the app shows.

A version may ask the researcher questions (`DocumentQuestion`, docs/specs/drafting.md). A
person's answer is a `document_question_answered` event (`answer`), given to a question of the
document's latest version. Question identifiers are derived from the gap a question fills, so
an answer stands until the person answers the same question again. `answers` gives the latest
answer to each question of the documents of a kind, which the conductor puts into the next
`DraftRequest`.

Where the project is in the Blueprint's process flow is derived from the log by `progress`, never
stored (`dd_harness.progress`, docs/specs/orchestration.md). The researcher's own word on it is two
events: `entry_chosen` (`choose_entry`, the last counts) and `step_marked` (`mark_step`: done,
skipped, or open again).

A project may have a title, given when it is created, so that a person can tell projects apart.
A conversation started from a project is a `conversation_started` event; `project_of` says which
project a conversation was started in, from an index of those events built when first asked.

Only owners will decide once membership is built, TODO(#389). Giving a drafter the version it
regenerates is TODO(#394); adding an inventory from the app is TODO(#395).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Literal, NoReturn

from dd_harness import progress as flow
from dd_harness.requirements import RE3DATA_ID, Requirements, RequirementsError
from dd_harness.sources import Sources
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    QUESTION_ID_PATTERN,
    UUID7_PATTERN,
    Document,
    DocumentKind,
    DocumentVersionRef,
    DraftAnswer,
    Envelope,
    FileInventory,
    OutcomeStatus,
    Principal,
    new_invocation_id,
    now,
)
from dd_sdk.evidence import INPUT_CANONICALISATION, canonicalise, input_hash

EVENTS_NAME = "events.jsonl"
BLOBS_DIR = ("blobs", "sha256")
PROJECT_CREATED = "project_created"
CONVERSATION_STARTED = "conversation_started"
INVENTORY_ADDED = "inventory_added"
REPOSITORY_CHOSEN = "repository_chosen"
DOCUMENT_VERSION_ADDED = "document_version_added"
DOCUMENT_VERSION_DECIDED = "document_version_decided"
DOCUMENT_CHANGE_REFUSED = "document_change_refused"
DOCUMENT_QUESTION_ANSWERED = "document_question_answered"
PROJECT_VALIDATED = "project_validated"
PACKAGE_BUILT = "package_built"
PROJECT_ID = re.compile(UUID7_PATTERN)
QUESTION_ID = re.compile(QUESTION_ID_PATTERN)
# Members every event has, which what an event carries never replaces.
_ENVELOPE_KEYS = frozenset({"event", "event_id", "project_id", "at", "acted_for", "caused_by"})
DIGEST = re.compile(r"[0-9a-f]{64}")

# A version's state (docs/specs/projects.md, invariant 11); a decision gives one of the last two.
PROPOSED: Final = "proposed"
APPROVED: Final = "approved"
REJECTED: Final = "rejected"
type Verdict = Literal["approved", "rejected"]
# The longest reason the harness keeps, in characters: room for a paragraph, not a document.
REASON_MAX_LENGTH = 2000
# The longest answer the harness keeps, in characters: a definition or a paragraph of methods.
ANSWER_MAX_LENGTH = 2000
# The longest project title the harness keeps, in characters: a name, not a description.
TITLE_MAX_LENGTH = 200


class ProjectError(ValueError):
    """The project does not exist, or what was to be added to it was refused."""


class UnknownProjectError(ProjectError):
    """No project has this identifier."""


class Refusal(StrEnum):
    """Why a decision, an edit or an answer was refused as not naming what it must
    (docs/specs/projects.md, invariant 12). Each value is a Problem Details slug."""

    NO_DOCUMENT = "document-not-found"
    NOT_LATEST = "version-not-latest"
    DECIDED = "version-decided"
    DIGEST = "digest-mismatch"
    NOT_ASKED = "question-not-asked"


class ChangeRefusedError(ProjectError):
    """A decision or edit that does not name the document's latest text, a decision on a
    version already decided, or an answer to a question the latest version does not ask. The
    refusal is recorded, and nothing else is."""

    def __init__(self, refusal: Refusal, detail: str) -> None:
        super().__init__(detail)
        self.refusal = refusal
        self.detail = detail


def text_digest(text: str) -> str:
    """The SHA-256 of a version's text as UTF-8: what a decision names as the text shown."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def reason_required(verdict: Verdict, *, edited: bool) -> bool:
    """Whether a decision must carry a reason. A departure from the draft does: rejecting it, or
    approving an edit of it. A plain approval does not (docs/specs/projects.md, invariant 13)."""
    return verdict == REJECTED or edited


def review_rules() -> dict[str, Any]:
    """The rule a decision form states, so that the app draws the harness's rule and holds none."""
    return {
        "reason_required": {
            "approved": reason_required(APPROVED, edited=False),
            "edited_and_approved": reason_required(APPROVED, edited=True),
            "rejected": reason_required(REJECTED, edited=False),
        },
        "reason_max_length": REASON_MAX_LENGTH,
    }


@dataclass(frozen=True)
class Decision:
    """What a person sent: the version they saw, the digest of its text as shown, their verdict
    and reason, and, to approve an edit of it, the edited text. It never names who decided."""

    document_id: str
    version: int
    digest: str
    verdict: Verdict
    reason: str | None = None
    edited_text: str | None = None

    @property
    def stated_reason(self) -> str | None:
        return (self.reason or "").strip() or None

    def check(self) -> None:
        """Raises `ProjectError` for a decision malformed in itself, which records nothing."""
        _check_names(self.document_id, self.digest)
        if self.verdict not in (APPROVED, REJECTED):
            raise ProjectError(f"a decision is {APPROVED!r} or {REJECTED!r}, not {self.verdict!r}")
        edited = self.edited_text is not None
        if edited and self.verdict == REJECTED:
            raise ProjectError("an edited text can be approved, not rejected")
        reason = self.stated_reason
        if reason is None and reason_required(self.verdict, edited=edited):
            raise ProjectError(f"{'approving an edit' if edited else 'rejecting'} needs a reason")
        if reason is not None and len(reason) > REASON_MAX_LENGTH:
            raise ProjectError(f"a reason is at most {REASON_MAX_LENGTH} characters")


def check_answers(answers: list[DraftAnswer]) -> list[DraftAnswer]:
    """The answers with their text stripped. Raises `ProjectError` for a set malformed in
    itself, which records nothing: none at all, a question named twice, or a blank or overlong
    answer."""
    if not answers:
        raise ProjectError("give at least one answer")
    named = [a.answered_question for a in answers]
    if len(set(named)) != len(named):
        raise ProjectError("each question is answered once")
    stripped = []
    for answer in answers:
        if not QUESTION_ID.fullmatch(answer.answered_question):
            raise ProjectError("a question is named by its identifier")
        text = answer.answer_text.strip()
        if not text:
            raise ProjectError(f"the answer to {answer.answered_question} is blank")
        if len(text) > ANSWER_MAX_LENGTH:
            raise ProjectError(f"an answer is at most {ANSWER_MAX_LENGTH} characters")
        stripped.append(DraftAnswer(answered_question=answer.answered_question, answer_text=text))
    return stripped


def _check_names(document_id: str, digest: str) -> None:
    """Raises `ProjectError` for a change that names no well-formed document or digest. Such a
    change is malformed in itself, so it records nothing, not even a refusal."""
    if not PROJECT_ID.fullmatch(document_id):
        raise ProjectError("a document is named by its UUIDv7")
    if not DIGEST.fullmatch(digest):
        raise ProjectError("a digest is a SHA-256 in lower-case hex")


class ProjectStore:
    """The file backend of `ProjectStorage` (`dd_harness.storage`, docs/specs/storage.md): each
    project's log and blobs under `root`. `root` belongs to this backend, for tests of its layout;
    every other caller reaches a project through `ProjectStorage`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        # Events of one project go in whole and in order, never interleaved, and a reader never
        # sees half of one. Each project has its own lock, so projects do not wait on each other.
        # A change checked against the log holds it from reading the log until its events are
        # written.
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        self._inventory_schema = ClassSchema.of(FileInventory)
        # Which project each conversation was started in: built from every log when first asked,
        # then kept up to date by `start_conversation`. TODO(#141): a scan of every log does not
        # scale past a deployment's worth of projects.
        self._conversations: dict[str, str] | None = None
        self._conversations_guard = threading.Lock()

    def _lock(self, project_id: str) -> threading.RLock:
        """The lock that serialises reads and writes of one project's log."""
        with self._locks_guard:
            return self._locks.setdefault(project_id, threading.RLock())

    def create(self, *, acted_for: Principal, caused_by: str, title: str | None = None) -> str:
        """A new project, and its `project_created` event. Returns its `project_id` (UUIDv7).

        Raises `ProjectError` for a title longer than `TITLE_MAX_LENGTH`; a blank title is none."""
        title = (title or "").strip() or None
        if title is not None and len(title) > TITLE_MAX_LENGTH:
            raise ProjectError(f"a project title is at most {TITLE_MAX_LENGTH} characters")
        project_id = new_invocation_id()
        (self.root / project_id).mkdir()
        detail = {"title": title} if title else {}
        self._append(project_id, PROJECT_CREATED, acted_for, caused_by, detail)
        return project_id

    def start_conversation(self, project_id: str, *, acted_for: Principal, caused_by: str) -> str:
        """A new conversation in the project, and its `conversation_started` event. Returns its
        `conversation_id` (UUIDv7). Raises `UnknownProjectError` for an unknown project."""
        self._require(project_id)
        conversation_id = new_invocation_id()
        index = self._conversation_index()
        self._append(
            project_id,
            CONVERSATION_STARTED,
            acted_for,
            caused_by,
            {"conversation_id": conversation_id},
        )
        with self._conversations_guard:
            index[conversation_id] = project_id
        return conversation_id

    def project_of(self, conversation_id: str) -> str | None:
        """The project the conversation was started in, or None if it was started in none."""
        return self._conversation_index().get(conversation_id)

    def projects(self) -> list[dict[str, Any]]:
        """A summary of every project, the one created first first (see `summary`)."""
        found = sorted(
            path.name for path in self.root.iterdir() if path.is_dir() and self.exists(path.name)
        )
        # UUIDv7s sort by the time they were made, so this is the order the projects were created.
        return [self.summary(project_id) for project_id in found]

    def summary(self, project_id: str) -> dict[str, Any]:
        """What a list of projects shows of one: its title, who created it and when, the latest
        inventory and repository chosen, how many conversations were started in it, and how many
        documents it has whose latest version is in each state. Raises `UnknownProjectError`."""
        events = self.events(project_id)
        created = events[0]
        inventory = next((e for e in reversed(events) if e["event"] == INVENTORY_ADDED), None)
        repository = next((e for e in reversed(events) if e["event"] == REPOSITORY_CHOSEN), None)
        states = {PROPOSED: 0, APPROVED: 0, REJECTED: 0}
        for document in self._fold(events).values():
            states[document["versions"][-1]["state"]] += 1
        return {
            "project_id": project_id,
            "title": created.get("title"),
            "created_at": created["at"],
            "created_by": created["acted_for"],
            "inventory": {
                "digest": inventory["digest"],
                "file_count": inventory["file_count"],
                "inventory_made_at": inventory["inventory_made_at"],
                "added_at": inventory["at"],
            }
            if inventory
            else None,
            "repository": {
                "re3data_id": repository["re3data_id"],
                "repository_name": repository["repository_name"],
                "warnings": repository["warnings"],
                "chosen_at": repository["at"],
            }
            if repository
            else None,
            "conversation_count": sum(1 for e in events if e["event"] == CONVERSATION_STARTED),
            "documents": states,
            "progress": flow.describe(events),
        }

    def _conversation_index(self) -> dict[str, str]:
        """Each conversation started in a project, and that project: read from every log once."""
        with self._conversations_guard:
            if self._conversations is None:
                index: dict[str, str] = {}
                for path in self.root.glob(f"*/{EVENTS_NAME}"):
                    project_id = path.parent.name
                    if not self.exists(project_id):
                        continue
                    for event in self.events(project_id):
                        if event["event"] == CONVERSATION_STARTED:
                            index[event["conversation_id"]] = project_id
                self._conversations = index
            return self._conversations

    def exists(self, project_id: str) -> bool:
        return bool(PROJECT_ID.fullmatch(project_id)) and self._events_path(project_id).is_file()

    def add_inventory(
        self,
        project_id: str,
        inventory: Mapping[str, Any],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Add a `FileInventory` to the project. Returns its digest.

        Raises `ProjectError` for an unknown project or a document the class schema refuses."""
        self._require(project_id)
        document = dict(inventory)
        errors = self._inventory_schema.errors(document)
        if errors:
            raise ProjectError(f"not a FileInventory: {'; '.join(errors)}")
        digest = input_hash(document)
        self._keep_blob(project_id, digest, canonicalise(document, INPUT_CANONICALISATION))
        files = document.get("inventory_files") or []
        self._append(
            project_id,
            INVENTORY_ADDED,
            acted_for,
            caused_by,
            {
                "digest": digest,
                "canonicalisation": INPUT_CANONICALISATION,
                "file_count": len(files),
                "inventory_made_at": document["inventory_made_at"],
            },
        )
        return digest

    def choose_repository(
        self,
        project_id: str,
        re3data_id: str,
        *,
        registry: Sources,
        requirements: Requirements,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Record the repository a researcher chose by its re3data identifier, and the
        requirements it resolved to. Its name and declared metadata standards come from the
        latest re3data export `registry` pins, and the event names that record by `snapshot_ref`
        and content hash (docs/specs/deposit.md). Returns the merged set's digest. Raises
        `ProjectError` for an unknown project, `RequirementsError` for an identifier the export
        does not hold, and `SourceConfigError` if no built export is pinned."""
        self._require(project_id)
        if not RE3DATA_ID.fullmatch(re3data_id):
            raise RequirementsError(f"{re3data_id!r} is not a re3data identifier (r3d + 9 digits)")
        entry = registry.re3data(re3data_id)
        if entry is None:
            raise RequirementsError(
                f"the pinned re3data export holds no repository {re3data_id}; "
                "check the identifier at re3data.org"
            )
        resolved = requirements.resolve(entry.re3data_id, entry.name, entry.metadata_standards)
        merged = resolved.requirements()
        digest = input_hash(merged)
        self._keep_blob(project_id, digest, canonicalise(merged, INPUT_CANONICALISATION))
        self._append(
            project_id,
            REPOSITORY_CHOSEN,
            acted_for,
            caused_by,
            {
                "re3data_id": resolved.re3data_id,
                "repository_name": resolved.repository_name,
                "declared_standards": list(resolved.declared_standards),
                "snapshot_ref": entry.snapshot_ref,
                "record_hash": entry.content_hash,
                "record_canonicalisation": entry.canonicalisation,
                "requirement_sets": [s.describe() for s in resolved.sets],
                "digest": digest,
                "canonicalisation": INPUT_CANONICALISATION,
                "warnings": list(resolved.warnings),
            },
        )
        return digest

    def choose_entry(
        self, project_id: str, entry: int, *, acted_for: Principal, caused_by: str
    ) -> None:
        """Record the Blueprint entry point (1, 2 or 3) the researcher chose; the last counts.
        Raises `ProjectError` for an unknown project or entry point."""
        self._require(project_id)
        if entry not in (1, 2, 3):
            raise ProjectError(f"the Blueprint has no entry point {entry!r}")
        self._append(project_id, flow.ENTRY_CHOSEN, acted_for, caused_by, {"entry": entry})

    def mark_step(
        self, project_id: str, step_id: str, mark: str, *, acted_for: Principal, caused_by: str
    ) -> None:
        """Record the researcher marking a process-flow step done, skipped, or open again.
        Raises `ProjectError` for an unknown project, a step that is not in scope, or a mark
        that is none of those."""
        self._require(project_id)
        if not flow.markable(step_id):
            raise ProjectError(f"{step_id!r} is not a process-flow step that may be marked")
        if mark not in flow.MARKS:
            raise ProjectError(f"a step is marked one of {', '.join(flow.MARKS)}, not {mark!r}")
        self._append(
            project_id,
            flow.STEP_MARKED,
            acted_for,
            caused_by,
            {"step_id": step_id, "mark": mark},
        )

    def progress(self, project_id: str) -> dict[str, Any]:
        """The entry point chosen and each step the log shows started, done or skipped. Raises
        `UnknownProjectError`."""
        return flow.describe(self.events(project_id))

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
        with self._lock(project_id):
            documents = self._documents(project_id)
            if document.revises is None:
                document_id, version = new_invocation_id(), 1
            else:
                revised = documents.get(document.revises.document_id)
                if revised is None or document.revises.version > len(revised["versions"]):
                    raise ProjectError(
                        f"run {envelope.invocation_id} revises no version of this project"
                    )
                if document.document_kind.value != revised["document_kind"]:
                    raise ProjectError(
                        f"run {envelope.invocation_id} revises a {revised['document_kind']} "
                        f"with a {document.document_kind.value}"
                    )
                document_id, version = revised["document_id"], len(revised["versions"]) + 1
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
            self._append(
                project_id,
                DOCUMENT_VERSION_ADDED,
                envelope.acting_for,
                envelope.invocation_id,
                detail,
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
        _check_names(document_id, digest)
        with self._lock(project_id):
            parent = self._check_latest(
                project_id, document_id, version, digest, acted_for, caused_by, deciding=False
            )
            detail = self._edited(project_id, parent, text)
            self._append(project_id, DOCUMENT_VERSION_ADDED, acted_for, caused_by, detail)
        return DocumentVersionRef(document_id=document_id, version=detail["version"])

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
        with self._lock(project_id):
            decided = self._check_latest(
                project_id,
                decision.document_id,
                decision.version,
                decision.digest,
                acted_for,
                caused_by,
                deciding=True,
            )
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
            self._write(project_id, events)
        return DocumentVersionRef(document_id=decided["document_id"], version=decided["version"])

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
        with self._lock(project_id):
            latest = self._check_latest(
                project_id, document_id, version, None, acted_for, caused_by, deciding=False
            )
            asked = {q["question_id"] for q in latest["questions"]}
            unasked = [a.answered_question for a in answers if a.answered_question not in asked]
            if unasked:
                self._refuse(
                    project_id,
                    acted_for,
                    caused_by,
                    {"document_id": document_id, "version": version, "questions": unasked},
                    Refusal.NOT_ASKED,
                    f"Version {version} does not ask {', '.join(unasked)}.",
                )
            self._write(
                project_id,
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

    def answers(self, project_id: str, document_kind: DocumentKind) -> list[dict[str, Any]] | None:
        """The answers a drafter of `document_kind` is given, as `DraftAnswer`s: the latest answer
        recorded to each question of any document of that kind, in the order last answered. None
        if there are none.

        A question's identifier is derived from the gap it fills, so it is the same in every
        draft of that kind. Until the conductor gives a drafter the version it regenerates,
        TODO(#394), each redraft is a new document, and an answer must outlive the document it
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
        found = list(self._documents(project_id).values())
        for document in found:
            for version in document["versions"]:
                blob = self._blob_path(project_id, version["digest"])
                version["text"] = blob.read_bytes().decode("utf-8")
        return found

    def events(self, project_id: str) -> list[dict[str, Any]]:
        """Every event of the project, oldest first. Raises `ProjectError` for an unknown one."""
        self._require(project_id)
        # Under the project's lock, so that an append being written is never read in part.
        with self._lock(project_id), self._events_path(project_id).open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def inventory(self, project_id: str) -> dict[str, Any] | None:
        """The inventory added last, or None if none has been."""
        return self._latest(project_id, INVENTORY_ADDED)

    def requirements(self, project_id: str) -> dict[str, Any] | None:
        """The merged requirements of the repository chosen last, or None if none has been."""
        return self._latest(project_id, REPOSITORY_CHOSEN)

    def metadata_record(self, project_id: str) -> dict[str, Any] | None:
        """The metadata record a person approved last, as an `ApprovedMetadataRecord`: the
        version named by the last approval in the log of any `metadata_record` document. None if
        no version of one has been approved. A later version proposed or rejected does not
        displace it."""
        events = self.events(project_id)
        documents = self._fold(events)
        for event in reversed(events):
            if event["event"] != DOCUMENT_VERSION_DECIDED or event["decision"] != APPROVED:
                continue
            document = documents[event["document_id"]]
            if document["document_kind"] != DocumentKind.METADATA_RECORD.value:
                continue
            version = document["versions"][event["version"] - 1]
            blob = self._blob_path(project_id, version["digest"])
            record: dict[str, Any] = {
                "version_ref": {"document_id": event["document_id"], "version": event["version"]},
                "media_type": version["media_type"],
                "document_text": blob.read_bytes().decode("utf-8"),
            }
            if version["conforms_to"] is not None:
                record["conforms_to"] = version["conforms_to"]
            return record
        return None

    def record_validation(
        self,
        project_id: str,
        report: Mapping[str, Any],
        *,
        conforms: bool,
        requirements_digest: str | None,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Keep a SHACL Validation Report of the project against its requirements
        (docs/specs/deposit.md, invariant 8), and its `project_validated` event. Returns the
        report's digest. Raises `ProjectError` for an unknown project."""
        self._require(project_id)
        document = dict(report)
        digest = input_hash(document)
        self._keep_blob(project_id, digest, canonicalise(document, INPUT_CANONICALISATION))
        self._append(
            project_id,
            PROJECT_VALIDATED,
            acted_for,
            caused_by,
            {
                "digest": digest,
                "canonicalisation": INPUT_CANONICALISATION,
                "conforms": conforms,
                "requirements_digest": requirements_digest,
            },
        )
        return digest

    def record_package(
        self,
        project_id: str,
        package: bytes,
        *,
        about: Mapping[str, Any],
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Keep a deposit package by the SHA-256 of its bytes, and its `package_built` event,
        which carries `about` (docs/specs/deposit.md, invariant 9). Returns the digest. Raises
        `ProjectError` for an unknown project."""
        self._require(project_id)
        digest = hashlib.sha256(package).hexdigest()
        self._keep_blob(project_id, digest, package)
        detail = {key: value for key, value in about.items() if key not in _ENVELOPE_KEYS}
        self._append(project_id, PACKAGE_BUILT, acted_for, caused_by, {**detail, "digest": digest})
        return digest

    def package(self, project_id: str, digest: str) -> bytes | None:
        """The bytes of a package the project log records as built, or None if it records no
        package with this digest. Raises `ProjectError` for an unknown project."""
        built = any(
            e["event"] == PACKAGE_BUILT and e["digest"] == digest for e in self.events(project_id)
        )
        if not built:
            return None
        return self._blob_path(project_id, digest).read_bytes()

    def _latest(self, project_id: str, kind: str) -> dict[str, Any] | None:
        """The blob the last event of `kind` kept, or None if there is no such event."""
        found = [e for e in self.events(project_id) if e["event"] == kind]
        if not found:
            return None
        blob = self._blob_path(project_id, found[-1]["digest"])
        data: dict[str, Any] = json.loads(blob.read_bytes())
        return data

    def _documents(self, project_id: str) -> dict[str, dict[str, Any]]:
        """The log folded into documents and the state of each version, without their text."""
        return self._fold(self.events(project_id))

    @staticmethod
    def _fold(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """`events` folded into documents and the state of each version, without their text."""
        documents: dict[str, dict[str, Any]] = {}
        for event in events:
            if event["event"] == DOCUMENT_VERSION_ADDED:
                document = documents.setdefault(
                    event["document_id"],
                    {
                        "document_id": event["document_id"],
                        "document_kind": event["document_kind"],
                        "versions": [],
                        "answers": [],
                    },
                )
                document["document_title"] = event.get("document_title")
                document["versions"].append(
                    {
                        "document_id": event["document_id"],
                        "document_kind": event["document_kind"],
                        "version": event["version"],
                        "digest": event["digest"],
                        "media_type": event["media_type"],
                        "document_title": event.get("document_title"),
                        "conforms_to": event.get("conforms_to"),
                        "revises": event.get("revises"),
                        "drafted_by": event.get("drafted_by"),
                        "questions": event.get("questions", []),
                        "added_by": event["acted_for"],
                        "added_at": event["at"],
                        "state": PROPOSED,
                        "decision": None,
                    }
                )
            elif event["event"] == DOCUMENT_VERSION_DECIDED:
                version = documents[event["document_id"]]["versions"][event["version"] - 1]
                version["state"] = event["decision"]
                version["decision"] = {
                    "reason": event.get("reason"),
                    "decided_by": event["acted_for"],
                    "decided_at": event["at"],
                }
            elif event["event"] == DOCUMENT_QUESTION_ANSWERED:
                document = documents[event["document_id"]]
                # The latest answer to a question stands; the order is the order last answered.
                kept = [a for a in document["answers"] if a["question_id"] != event["question_id"]]
                document["answers"] = [
                    *kept,
                    {
                        "question_id": event["question_id"],
                        "answer_text": event["answer_text"],
                        "version": event["version"],
                        "answered_by": event["acted_for"],
                        "answered_at": event["at"],
                    },
                ]
        return documents

    def _check_latest(
        self,
        project_id: str,
        document_id: str,
        version: int,
        digest: str | None,
        acted_for: Principal,
        caused_by: str,
        *,
        deciding: bool,
    ) -> dict[str, Any]:
        """The version a change names, if it is its document's latest, has this digest (unless
        `digest` is None, for an answer, which names no text) and, for a decision, is undecided.
        Otherwise records the refusal and raises `ChangeRefusedError`. Called with the lock
        held."""
        document = self._documents(project_id).get(document_id)
        latest: dict[str, Any] | None = document["versions"][-1] if document else None
        if latest is None:
            refusal, detail = Refusal.NO_DOCUMENT, f"This project has no document {document_id!r}."
        elif version != latest["version"]:
            refusal = Refusal.NOT_LATEST
            detail = f"Version {version} is not the latest: version {latest['version']} is."
        elif deciding and latest["state"] != PROPOSED:
            refusal = Refusal.DECIDED
            detail = f"Version {version} has already been {latest['state']}."
        elif digest is not None and digest != latest["digest"]:
            refusal = Refusal.DIGEST
            detail = f"The text sent as shown is not the text of version {version}."
        else:
            return latest
        named = {"document_id": document_id, "version": version}
        if digest is not None:
            named["digest"] = digest
        if latest:
            named["latest_version"] = latest["version"]
        self._refuse(project_id, acted_for, caused_by, named, refusal, detail)

    def _refuse(
        self,
        project_id: str,
        acted_for: Principal,
        caused_by: str,
        named: dict[str, Any],
        refusal: Refusal,
        detail: str,
    ) -> NoReturn:
        """Record a `document_change_refused` event and raise `ChangeRefusedError`."""
        self._append(
            project_id,
            DOCUMENT_CHANGE_REFUSED,
            acted_for,
            caused_by,
            {**named, "refusal": refusal.value},
        )
        raise ChangeRefusedError(refusal, detail)

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

    def _require(self, project_id: str) -> None:
        if not self.exists(project_id):
            raise UnknownProjectError(f"no project {project_id!r}")

    def _events_path(self, project_id: str) -> Path:
        return self.root / project_id / EVENTS_NAME

    def _blob_path(self, project_id: str, digest: str) -> Path:
        return self.root.joinpath(project_id, *BLOBS_DIR, digest)

    def _append(
        self,
        project_id: str,
        kind: str,
        acted_for: Principal,
        caused_by: str,
        detail: dict[str, Any],
    ) -> None:
        self._write(project_id, [self._event(project_id, kind, acted_for, caused_by, detail)])

    @staticmethod
    def _event(
        project_id: str, kind: str, acted_for: Principal, caused_by: str, detail: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "event": kind,
            "event_id": new_invocation_id(),
            "project_id": project_id,
            "at": now().isoformat(),
            "acted_for": acted_for.model_dump(mode="json", exclude_none=True),
            "caused_by": caused_by,
            **detail,
        }

    def _write(self, project_id: str, events: list[dict[str, Any]]) -> None:
        """Append `events` in one write, flushed to disk before returning, so that events made
        together, such as an edit and its approval, go in together."""
        text = "".join(
            json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n" for event in events
        )
        path = self._events_path(project_id)
        with self._lock(project_id), path.open("a", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())

    def _keep_blob(self, project_id: str, digest: str, content: bytes) -> None:
        """Write content once, under its digest; content already kept is left as it is."""
        path = self._blob_path(project_id, digest)
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written aside and moved into place, so a reader never sees half a blob.
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(content)
            Path(tmp).replace(path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

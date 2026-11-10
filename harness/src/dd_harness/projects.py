"""The project record: an append-only log of what changed in a project (docs/specs/projects.md).

A project is a record of its own that outlives any conversation. These are the project rules,
written once over a `ProjectLog` (`dd_harness.storage`, docs/specs/storage.md) that a backend
provides and that only stores: `Projects` is the rules, and `ProjectStore` the rules over the
file log, `dd_harness.project_files`, under `DD_PROJECTS_DIR`.

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
skipped, or open again). An orchestrator's model may also record an `entry_chosen` it worked out
from what the researcher said, saying so in `entry_source`, until the researcher chooses one.

A project may have a title, so that a person can tell projects apart. A person gives it when
creating the project or renames it later; while no person has, an orchestrator's model may name
it (`rename`, a `project_renamed` event saying which). The latest title counts, and a model's is
refused once a person has given one.
A researcher may attach a supporting document, such as a protocol or a codebook, as text: a
`documentation_added` event names it, its media type and size, and the SHA-256 of its UTF-8
text, under which the text is kept as a blob (`add_documentation`). Only plain text and Markdown
within `DOCUMENTATION_MAX_BYTES` are kept, and a name is a file name, never a path. Attaching the
same text again under the same name records nothing new in `documentation`, which lists each
document once, the one added first first.

A conversation started from a project is a `conversation_started` event; `project_of` says which
project a conversation was started in, from what the logs hold when asked.

Who may do what in a project is read from the log by `dd_harness.project_access`; membership
events are TODO(#389). Giving a drafter the version it
regenerates is TODO(#394).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

from dd_harness import progress as flow
from dd_harness.project_files import FileProjectLog
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

if TYPE_CHECKING:
    from dd_harness.storage import ProjectLog, ProjectSection

PROJECT_CREATED = "project_created"
PROJECT_RENAMED = "project_renamed"
CONVERSATION_STARTED = "conversation_started"
INVENTORY_ADDED = "inventory_added"
DOCUMENTATION_ADDED = "documentation_added"
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
# What documentation a project keeps (docs/specs/projects.md): text a person can read, within a
# size a document about the data needs and a dataset rarely fits.
DOCUMENTATION_MEDIA_TYPES: Final = ("text/plain", "text/markdown")
DOCUMENTATION_MAX_BYTES: Final = 256 * 1024
# The longest name a document is kept under, in characters: a file name.
DOCUMENTATION_NAME_MAX_LENGTH: Final = 255
# Who gave a project its title: a person (when creating or renaming it) or an orchestrator's
# model. A person's title is never replaced by a model's.
TITLE_BY_RESEARCHER: Final = "researcher"
TITLE_BY_MODEL: Final = "model"
type TitleSource = Literal["researcher", "model"]


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


@dataclass(frozen=True)
class Refused:
    """A change the project rules refuse: why, what a person is told, and what the
    `document_change_refused` event names. Returned, not raised, so that the refusal is written
    in the change's exclusive section before `ChangeRefusedError` is raised."""

    refusal: Refusal
    detail: str
    named: dict[str, Any]


def text_digest(text: str) -> str:
    """The SHA-256 of a version's text as UTF-8: what a decision names as the text shown."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_documentation(name: str, media_type: str, text: str) -> None:
    """Raise `ProjectError` for a document the project would not keep (`add_documentation`), so
    that a caller adding more than one thing can refuse all of it before adding any."""
    if media_type not in DOCUMENTATION_MEDIA_TYPES:
        raise ProjectError(
            f"a document is {' or '.join(DOCUMENTATION_MEDIA_TYPES)}, not {media_type!r}"
        )
    _check_documentation_name(name)
    if not text.strip():
        raise ProjectError("a document may not be blank")
    size = len(text.encode("utf-8"))
    if size > DOCUMENTATION_MAX_BYTES:
        raise ProjectError(f"a document may be at most {DOCUMENTATION_MAX_BYTES} bytes, not {size}")


def _check_documentation_name(name: str) -> None:
    """Refuse a document name that is blank, too long, or names a folder."""
    if not name.strip():
        raise ProjectError("a document needs a name")
    if len(name) > DOCUMENTATION_NAME_MAX_LENGTH:
        raise ProjectError(
            f"a document's name may be at most {DOCUMENTATION_NAME_MAX_LENGTH} characters"
        )
    if "/" in name or "\\" in name or name in (".", "..") or any(ord(c) < 32 for c in name):
        raise ProjectError("a document's name is a file name, without any folder")


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


def _check_title(title: str) -> None:
    if len(title) > TITLE_MAX_LENGTH:
        raise ProjectError(f"a project title is at most {TITLE_MAX_LENGTH} characters")


def _title(events: list[dict[str, Any]]) -> tuple[str | None, TitleSource | None]:
    """A project's latest title and who gave it: a title given at creation is a person's."""
    for event in reversed(events):
        if event["event"] == PROJECT_RENAMED:
            return event["title"], event["title_source"]
        if event["event"] == PROJECT_CREATED and event.get("title"):
            return event["title"], TITLE_BY_RESEARCHER
    return None, None


def _check_names(document_id: str, digest: str) -> None:
    """Raises `ProjectError` for a change that names no well-formed document or digest. Such a
    change is malformed in itself, so it records nothing, not even a refusal."""
    if not PROJECT_ID.fullmatch(document_id):
        raise ProjectError("a document is named by its UUIDv7")
    if not DIGEST.fullmatch(digest):
        raise ProjectError("a digest is a SHA-256 in lower-case hex")


class Projects:
    """The project rules, written once over a `ProjectLog` (`dd_harness.storage`,
    docs/specs/storage.md): the `ProjectStorage` every backend gives its callers. The log stores
    and reads; everything that decides whether a change is allowed, and what the log means, is
    here."""

    def __init__(self, log: ProjectLog) -> None:
        self.log = log
        self._inventory_schema = ClassSchema.of(FileInventory)

    def create(self, *, acted_for: Principal, caused_by: str, title: str | None = None) -> str:
        """A new project, and its `project_created` event. Returns its `project_id` (UUIDv7).

        Raises `ProjectError` for a title longer than `TITLE_MAX_LENGTH`; a blank title is none."""
        title = (title or "").strip() or None
        if title is not None:
            _check_title(title)
        project_id = new_invocation_id()
        detail = {"title": title} if title else {}
        self.log.create(
            project_id, self._event(project_id, PROJECT_CREATED, acted_for, caused_by, detail)
        )
        return project_id

    def rename(
        self,
        project_id: str,
        title: str,
        *,
        source: TitleSource,
        acted_for: Principal,
        caused_by: str,
    ) -> bool:
        """Give the project a new title, a `project_renamed` event saying who gave it. Returns
        False, and records nothing, for a model's title once a person has given one. Raises
        `ProjectError` for an unknown project, a blank title, one longer than
        `TITLE_MAX_LENGTH` or a source that is neither."""
        if source not in (TITLE_BY_RESEARCHER, TITLE_BY_MODEL):
            raise ProjectError(f"a title is given by a researcher or a model, not {source!r}")
        title = title.strip()
        if not title:
            raise ProjectError("a project title may not be blank")
        _check_title(title)
        with self._section(project_id) as section:
            _, held = _title(section.events())
            if source == TITLE_BY_MODEL and held == TITLE_BY_RESEARCHER:
                return False
            detail = {"title": title, "title_source": source}
            section.append([self._event(project_id, PROJECT_RENAMED, acted_for, caused_by, detail)])
        return True

    def start_conversation(self, project_id: str, *, acted_for: Principal, caused_by: str) -> str:
        """A new conversation in the project, and its `conversation_started` event. Returns its
        `conversation_id` (UUIDv7). Raises `UnknownProjectError` for an unknown project."""
        conversation_id = new_invocation_id()
        self._append(
            project_id,
            CONVERSATION_STARTED,
            acted_for,
            caused_by,
            {"conversation_id": conversation_id},
        )
        return conversation_id

    def project_of(self, conversation_id: str) -> str | None:
        """The project the conversation was started in, or None if the logs record it in none
        when asked."""
        return self.log.project_of(conversation_id)

    def projects(self) -> list[dict[str, Any]]:
        """A summary of every project, the one created first first (see `summary`)."""
        return [self.summary(project_id) for project_id in self.log.project_ids()]

    def summary(self, project_id: str) -> dict[str, Any]:
        """What a list of projects shows of one: its latest title and who gave it (`title_source`:
        `researcher`, `model`, or None while it has none), who created it and when, the latest
        inventory and repository chosen, how many conversations were started in it, and how many
        documents it has whose latest version is in each state. Raises `UnknownProjectError`."""
        events = self.events(project_id)
        created = events[0]
        title, title_source = _title(events)
        inventory = next((e for e in reversed(events) if e["event"] == INVENTORY_ADDED), None)
        repository = next((e for e in reversed(events) if e["event"] == REPOSITORY_CHOSEN), None)
        states = {PROPOSED: 0, APPROVED: 0, REJECTED: 0}
        for document in _fold(events).values():
            states[document["versions"][-1]["state"]] += 1
        return {
            "project_id": project_id,
            "title": title,
            "title_source": title_source,
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

    def exists(self, project_id: str) -> bool:
        return bool(PROJECT_ID.fullmatch(project_id)) and self.log.exists(project_id)

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

    def add_documentation(
        self,
        project_id: str,
        name: str,
        media_type: str,
        text: str,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Add a supporting document's text to the project. Returns the SHA-256 of its UTF-8 text.

        Raises `ProjectError` for an unknown project, a media type outside
        `DOCUMENTATION_MEDIA_TYPES`, a blank text or one over `DOCUMENTATION_MAX_BYTES`, or a name
        that is blank, too long, or holds a folder. What is refused leaves no trace."""
        self._require(project_id)
        check_documentation(name, media_type, text)
        content = text.encode("utf-8")
        digest = text_digest(text)
        self._keep_blob(project_id, digest, content)
        self._append(
            project_id,
            DOCUMENTATION_ADDED,
            acted_for,
            caused_by,
            {"name": name, "media_type": media_type, "size": len(content), "digest": digest},
        )
        return digest

    def documentation(self, project_id: str) -> list[dict[str, Any]]:
        """Each document the project holds, without its text, as a `DocumentationSummary`: the
        one added first first, and a name and text added again listed once, when first added.
        Raises `UnknownProjectError` for an unknown project."""
        found: dict[tuple[str, str], dict[str, Any]] = {}
        for event in self.events(project_id):
            if event["event"] != DOCUMENTATION_ADDED:
                continue
            found.setdefault(
                (event["name"], event["digest"]),
                {
                    "documentation_name": event["name"],
                    "documentation_digest": event["digest"],
                    "documentation_media_type": event["media_type"],
                    "documentation_size": event["size"],
                    "documentation_added_at": event["at"],
                },
            )
        return list(found.values())

    def documentation_text(self, project_id: str, digest: str) -> str | None:
        """The text of the project's document with this digest, or None if it holds none.
        Raises `UnknownProjectError` for an unknown project."""
        held = {e["digest"] for e in self.events(project_id) if e["event"] == DOCUMENTATION_ADDED}
        if digest not in held:
            return None
        return self._blob(project_id, digest).decode("utf-8")

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
        self,
        project_id: str,
        entry: int,
        *,
        acted_for: Principal,
        caused_by: str,
        source: flow.EntrySource = flow.ENTRY_BY_RESEARCHER,
    ) -> bool:
        """Record the Blueprint entry point (1, 2 or 3) the researcher chose, or an
        orchestrator's model worked out from what they said; the last counts. Returns False, and
        records nothing, for a model's entry point once the researcher has chosen one. Raises
        `ProjectError` for an unknown project, entry point or source."""
        if source not in (flow.ENTRY_BY_RESEARCHER, flow.ENTRY_BY_MODEL):
            raise ProjectError(
                f"an entry point is chosen by a researcher or a model, not {source!r}"
            )
        if entry not in (1, 2, 3):
            raise ProjectError(f"the Blueprint has no entry point {entry!r}")
        with self._section(project_id) as section:
            _, held = flow.entry_and_source(section.events())
            if source == flow.ENTRY_BY_MODEL and held == flow.ENTRY_BY_RESEARCHER:
                return False
            detail = {"entry": entry, "entry_source": source}
            section.append(
                [self._event(project_id, flow.ENTRY_CHOSEN, acted_for, caused_by, detail)]
            )
        return True

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
        with self._section(project_id) as section:
            documents = _fold(section.events())
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
        _check_names(document_id, digest)

        def change(section: ProjectSection) -> DocumentVersionRef | Refused:
            parent = _check_latest(section.events(), document_id, version, digest, deciding=False)
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
            decided = _check_latest(
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
            latest = _check_latest(section.events(), document_id, version, None, deciding=False)
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
        found = list(self._documents(project_id).values())
        for document in found:
            for version in document["versions"]:
                version["text"] = self._blob(project_id, version["digest"]).decode("utf-8")
        return found

    def inventory(self, project_id: str) -> dict[str, Any] | None:
        """The inventory added last, or None if none has been."""
        return self._latest(project_id, INVENTORY_ADDED)

    def requirements(self, project_id: str) -> dict[str, Any] | None:
        """The merged requirements of the repository chosen last, or None if none has been."""
        return self._latest(project_id, REPOSITORY_CHOSEN)

    def current_version(
        self, project_id: str, document_kind: DocumentKind, document_id: str | None = None
    ) -> dict[str, Any] | None:
        """The version a drafter of `document_kind` regenerates, as a `CurrentVersion`: the latest
        version of `document_id`, or, without one, of the project's document of that kind drafted
        or revised last. Its text, its state, and the reason a person gave for any decision on it.
        None if the project holds no document of the kind.

        Raises `ProjectError` if `document_id` names no document of this project, or one of
        another kind, and `UnknownProjectError` for an unknown project."""
        documents = self._documents(project_id)
        if document_id is not None:
            named = documents.get(document_id)
            if named is None:
                raise ProjectError(f"this project has no document {document_id!r}")
            if named["document_kind"] != document_kind.value:
                raise ProjectError(
                    f"document {document_id!r} is a {named['document_kind']}, "
                    f"not a {document_kind.value}"
                )
            chosen: dict[str, Any] | None = named
        else:
            # The last version added of the kind names the document drafted or revised last.
            chosen = None
            for event in self.events(project_id):
                if (
                    event["event"] == DOCUMENT_VERSION_ADDED
                    and event["document_kind"] == document_kind.value
                ):
                    chosen = documents[event["document_id"]]
        if chosen is None:
            return None
        latest: dict[str, Any] = chosen["versions"][-1]
        given: dict[str, Any] = {
            "version_ref": {"document_id": chosen["document_id"], "version": latest["version"]},
            "media_type": latest["media_type"],
            "document_text": self._blob(project_id, latest["digest"]).decode("utf-8"),
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
        documents = _fold(events)
        for event in reversed(events):
            if event["event"] != DOCUMENT_VERSION_DECIDED or event["decision"] != APPROVED:
                continue
            document = documents[event["document_id"]]
            if document["document_kind"] != DocumentKind.METADATA_RECORD.value:
                continue
            version = document["versions"][event["version"] - 1]
            text = self._blob(project_id, version["digest"]).decode("utf-8")
            record: dict[str, Any] = {
                "version_ref": {"document_id": event["document_id"], "version": event["version"]},
                "media_type": version["media_type"],
                "document_text": text,
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
        return self._blob(project_id, digest)

    def events(self, project_id: str) -> list[dict[str, Any]]:
        """Every event of the project, oldest first. Raises `ProjectError` for an unknown one."""
        self._require(project_id)
        try:
            return self.log.events(project_id)
        except KeyError:
            raise UnknownProjectError(f"no project {project_id!r}") from None

    def _latest(self, project_id: str, kind: str) -> dict[str, Any] | None:
        """The blob the last event of `kind` kept, or None if there is no such event."""
        found = [e for e in self.events(project_id) if e["event"] == kind]
        if not found:
            return None
        data: dict[str, Any] = json.loads(self._blob(project_id, found[-1]["digest"]))
        return data

    def _documents(self, project_id: str) -> dict[str, dict[str, Any]]:
        """The log folded into documents and the state of each version, without their text."""
        return _fold(self.events(project_id))

    @contextmanager
    def _section(self, project_id: str) -> Iterator[ProjectSection]:
        """The project's exclusive section in the log. Raises `UnknownProjectError`."""
        self._require(project_id)
        with self.log.section(project_id) as section:
            yield section

    def _checked[T](
        self,
        project_id: str,
        acted_for: Principal,
        caused_by: str,
        change: Callable[[ProjectSection], T | Refused],
    ) -> T:
        """Run `change` in the project's exclusive section (docs/specs/storage.md, invariant
        10). If it returns a refusal, its `document_change_refused` event is appended in the
        section, and `ChangeRefusedError` is raised once the section has ended, so the refusal
        is kept whether or not a backend undoes a section that raises (invariant 11). A
        `ProjectError` that `change` raises records nothing."""
        with self._section(project_id) as section:
            result = change(section)
            if isinstance(result, Refused):
                section.append(
                    [
                        self._event(
                            project_id,
                            DOCUMENT_CHANGE_REFUSED,
                            acted_for,
                            caused_by,
                            {**result.named, "refusal": result.refusal.value},
                        )
                    ]
                )
        if isinstance(result, Refused):
            raise ChangeRefusedError(result.refusal, result.detail)
        return result

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

    def _keep_blob(self, project_id: str, digest: str, content: bytes) -> None:
        self.log.keep_blob(project_id, digest, content)

    def _blob(self, project_id: str, digest: str) -> bytes:
        """Content an event of the project names. The log keeps it before the event is appended,
        so a missing blob is a damaged store, not a refusal."""
        content = self.log.blob(project_id, digest)
        if content is None:
            raise LookupError(f"project {project_id} keeps no content {digest}")
        return content

    def _append(
        self,
        project_id: str,
        kind: str,
        acted_for: Principal,
        caused_by: str,
        detail: dict[str, Any],
    ) -> None:
        """Append one event that no rule checks against the log, in its own section."""
        with self._section(project_id) as section:
            section.append([self._event(project_id, kind, acted_for, caused_by, detail)])

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


class ProjectStore(Projects):
    """The file backend of `ProjectStorage`: the project rules over a `FileProjectLog` under
    `root` (`dd_harness.project_files`, docs/specs/storage.md). `root` belongs to this backend,
    for tests of its layout; every other caller reaches a project through `ProjectStorage`."""

    def __init__(self, root: Path) -> None:
        super().__init__(FileProjectLog(root))
        self.root = root


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
    events: list[dict[str, Any]],
    document_id: str,
    version: int,
    digest: str | None,
    *,
    deciding: bool,
) -> dict[str, Any] | Refused:
    """The version a change names, if it is its document's latest, has this digest (unless
    `digest` is None, for an answer, which names no text) and, for a decision, is undecided.
    Otherwise the refusal, which `Projects._checked` records. `events` is the log as the
    change's exclusive section reads it."""
    document = _fold(events).get(document_id)
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
    return Refused(refusal, detail, named)

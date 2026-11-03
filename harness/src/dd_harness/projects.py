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

Only owners will decide once membership is built, TODO(#389). The conductor recording each draft,
giving an agent the project's facts, and naming the run that caused an event, is TODO(#394);
adding an inventory from the app is TODO(#395).
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
from typing import Any, Final, Literal

from dd_harness.requirements import Resolved
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    UUID7_PATTERN,
    Document,
    DocumentVersionRef,
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
INVENTORY_ADDED = "inventory_added"
REPOSITORY_CHOSEN = "repository_chosen"
DOCUMENT_VERSION_ADDED = "document_version_added"
DOCUMENT_VERSION_DECIDED = "document_version_decided"
DOCUMENT_CHANGE_REFUSED = "document_change_refused"
PROJECT_ID = re.compile(UUID7_PATTERN)
DIGEST = re.compile(r"[0-9a-f]{64}")

# A version's state (docs/specs/projects.md, invariant 11); a decision gives one of the last two.
PROPOSED: Final = "proposed"
APPROVED: Final = "approved"
REJECTED: Final = "rejected"
type Verdict = Literal["approved", "rejected"]
# The longest reason the harness keeps, in characters: room for a paragraph, not a document.
REASON_MAX_LENGTH = 2000


class ProjectError(ValueError):
    """The project does not exist, or what was to be added to it was refused."""


class UnknownProjectError(ProjectError):
    """No project has this identifier."""


class Refusal(StrEnum):
    """Why a decision or an edit was refused as not naming the text it must
    (docs/specs/projects.md, invariant 12). Each value is a Problem Details slug."""

    NO_DOCUMENT = "document-not-found"
    NOT_LATEST = "version-not-latest"
    DECIDED = "version-decided"
    DIGEST = "digest-mismatch"


class ChangeRefusedError(ProjectError):
    """A decision or edit that does not name the document's latest text, or a decision on a
    version already decided. The refusal is recorded, and nothing else is."""

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


def _check_names(document_id: str, digest: str) -> None:
    """Raises `ProjectError` for a change that names no well-formed document or digest. Such a
    change is malformed in itself, so it records nothing, not even a refusal."""
    if not PROJECT_ID.fullmatch(document_id):
        raise ProjectError("a document is named by its UUIDv7")
    if not DIGEST.fullmatch(digest):
        raise ProjectError("a digest is a SHA-256 in lower-case hex")


class ProjectStore:
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

    def _lock(self, project_id: str) -> threading.RLock:
        """The lock that serialises reads and writes of one project's log."""
        with self._locks_guard:
            return self._locks.setdefault(project_id, threading.RLock())

    def create(self, *, acted_for: Principal, caused_by: str) -> str:
        """A new project, and its `project_created` event. Returns its `project_id` (UUIDv7)."""
        project_id = new_invocation_id()
        (self.root / project_id).mkdir()
        self._append(project_id, PROJECT_CREATED, acted_for, caused_by, {})
        return project_id

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
        self, project_id: str, resolved: Resolved, *, acted_for: Principal, caused_by: str
    ) -> str:
        """Record the repository a researcher chose, and the requirements it resolved to.
        Returns the merged set's digest. Raises `ProjectError` for an unknown project."""
        self._require(project_id)
        requirements = resolved.requirements()
        digest = input_hash(requirements)
        self._keep_blob(project_id, digest, canonicalise(requirements, INPUT_CANONICALISATION))
        self._append(
            project_id,
            REPOSITORY_CHOSEN,
            acted_for,
            caused_by,
            {
                "re3data_id": resolved.re3data_id,
                "repository_name": resolved.repository_name,
                "declared_standards": list(resolved.declared_standards),
                "requirement_sets": [s.describe() for s in resolved.sets],
                "digest": digest,
                "canonicalisation": INPUT_CANONICALISATION,
                "warnings": list(resolved.warnings),
            },
        )
        return digest

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
        documents: dict[str, dict[str, Any]] = {}
        for event in self.events(project_id):
            if event["event"] == DOCUMENT_VERSION_ADDED:
                document = documents.setdefault(
                    event["document_id"],
                    {
                        "document_id": event["document_id"],
                        "document_kind": event["document_kind"],
                        "versions": [],
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
        return documents

    def _check_latest(
        self,
        project_id: str,
        document_id: str,
        version: int,
        digest: str,
        acted_for: Principal,
        caused_by: str,
        *,
        deciding: bool,
    ) -> dict[str, Any]:
        """The version a change names, if it is its document's latest, has this digest and, for a
        decision, is undecided. Otherwise records the refusal and raises `ChangeRefusedError`.
        Called with the lock held."""
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
        elif digest != latest["digest"]:
            refusal = Refusal.DIGEST
            detail = f"The text sent as shown is not the text of version {version}."
        else:
            return latest
        self._append(
            project_id,
            DOCUMENT_CHANGE_REFUSED,
            acted_for,
            caused_by,
            {
                "document_id": document_id,
                "version": version,
                "digest": digest,
                "refusal": refusal.value,
                **({"latest_version": latest["version"]} if latest else {}),
            },
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

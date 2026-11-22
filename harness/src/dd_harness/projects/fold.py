"""The one fold of a project's log into its documents, and the check every change to a document
makes against it (docs/specs/projects.md, invariants 9 to 15).

A document is a sequence of versions, each a `document_version_added` event whose text is kept as
a blob under the SHA-256 of its UTF-8 bytes. Every version begins `proposed`, and one
`document_version_decided` makes it `approved` or `rejected` for good. `fold` reads the log into
each document and the state of each of its versions, without their text.
"""

from __future__ import annotations

import hashlib
from typing import Any, Final

from dd_harness.projects.rules import (
    DOCUMENT_QUESTION_ANSWERED,
    DOCUMENT_REVISION_REQUESTED,
    DOCUMENT_VERSION_ADDED,
    DOCUMENT_VERSION_DECIDED,
    Refusal,
    Refused,
)

# A version's state (docs/specs/projects.md, invariant 11); a decision gives one of the last two.
PROPOSED: Final = "proposed"
APPROVED: Final = "approved"
REJECTED: Final = "rejected"
# A version's stage (docs/specs/drafting.md): only a draft can be decided. An event that records
# no stage is of a draft.
DRAFT_STAGE: Final = "draft"


def text_digest(text: str) -> str:
    """The SHA-256 of a version's text as UTF-8: what a decision names as the text shown."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fold(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """`events` folded into documents and the state of each version, without their text."""
    documents: dict[str, dict[str, Any]] = {}
    for event in events:
        if event["event"] == DOCUMENT_VERSION_ADDED:
            _add_version(documents, event)
        elif event["event"] == DOCUMENT_VERSION_DECIDED:
            version = documents[event["document_id"]]["versions"][event["version"] - 1]
            version["state"] = event["decision"]
            version["decision"] = {
                "reason": event.get("reason"),
                "decided_by": event["acted_for"],
                "decided_at": event["at"],
            }
        elif event["event"] == DOCUMENT_REVISION_REQUESTED:
            # The change a person asked for last to a version stands (docs/specs/drafting.md).
            version = documents[event["document_id"]]["versions"][event["version"] - 1]
            version["revision_request"] = {
                "instruction": event["instruction"],
                "requested_by": event["acted_for"],
                "requested_at": event["at"],
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


def _add_version(documents: dict[str, dict[str, Any]], event: dict[str, Any]) -> None:
    """Fold one `document_version_added` event into its document, as a proposed version."""
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
            **({"acting_as": event["acting_as"]} if event.get("acting_as") else {}),
            "questions": event.get("questions", []),
            "stage": event.get("stage", DRAFT_STAGE),
            "added_by": event["acted_for"],
            "added_at": event["at"],
            "state": PROPOSED,
            "decision": None,
            "revision_request": None,
        }
    )


def check_latest(
    events: list[dict[str, Any]],
    document_id: str,
    version: int,
    digest: str | None,
    *,
    deciding: bool,
) -> dict[str, Any] | Refused:
    """The version a change names, if it is its document's latest, has this digest (unless
    `digest` is None, for an answer, which names no text) and, for a decision, is undecided.
    Otherwise the refusal, which `ProjectRules._checked` records. `events` is the log as the
    change's exclusive section reads it."""
    document = fold(events).get(document_id)
    latest: dict[str, Any] | None = document["versions"][-1] if document else None
    if latest is None:
        refusal, detail = Refusal.NO_DOCUMENT, f"This project has no document {document_id!r}."
    elif version != latest["version"]:
        refusal = Refusal.NOT_LATEST
        detail = f"Version {version} is not the latest: version {latest['version']} is."
    elif deciding and latest["state"] != PROPOSED:
        refusal = Refusal.DECIDED
        detail = f"Version {version} has already been {latest['state']}."
    elif deciding and latest["stage"] != DRAFT_STAGE:
        refusal = Refusal.NOT_A_DRAFT
        detail = (
            f"Version {version} only asks what the drafter needs before it writes the document: "
            "answer its questions and ask for the document to be drafted."
        )
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

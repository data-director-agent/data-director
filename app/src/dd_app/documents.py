"""A project's documents as the shell draws them, and a person's decision or answers as the
harness takes them (docs/specs/projects.md, docs/specs/drafting.md).

The harness decides and records (`dd_harness.projects`). The app reads back what the log holds,
together with the harness's rules for decisions and answers, and passes a person's decision or
answers on unchanged except for their shape. Neither request names who decided or answered: the
server gives the store the principal its authenticator names.
"""

from __future__ import annotations

import re
from typing import Any

from dd_harness.projects import (
    ANSWER_MAX_LENGTH,
    APPROVED,
    REJECTED,
    REQUEST_MAX_LENGTH,
    Decision,
    Verdict,
    review_rules,
)
from dd_harness.storage import ProjectDocuments
from dd_sdk.contract.models import QUESTION_ID_PATTERN, UUID7_PATTERN, DraftAnswer

DIGEST = re.compile(r"[0-9a-f]{64}")
DOCUMENT_ID = re.compile(UUID7_PATTERN)
# What a decision request may give; anything else, such as a decider, is refused.
DECISION_FIELDS = frozenset({"version", "digest", "decision", "reason", "edited_text"})
# What an answers request may give, and what each answer may; anything else, such as who
# answered, is refused.
ANSWERS_FIELDS = frozenset({"version", "answers"})
ANSWER_FIELDS = frozenset({"answered_question", "answer_text"})
QUESTION_ID = re.compile(QUESTION_ID_PATTERN)


class DecisionRequestError(ValueError):
    """A decision or answers request the shell should never send: malformed, so nothing is
    recorded."""


def view(store: ProjectDocuments, project_id: str) -> dict[str, Any]:
    """`GET /api/projects/{id}/documents`: each document with every version and its state, the
    answers given to its questions, and the rules a decision or answer form states. Raises
    `UnknownProjectError` for an unknown project."""
    return {
        "project_id": project_id,
        "documents": store.documents(project_id),
        "review": review_rules(),
        "answer_max_length": ANSWER_MAX_LENGTH,
        "request_max_length": REQUEST_MAX_LENGTH,
    }


def parse_decision(document_id: str, body: object) -> Decision:
    """The decision a `POST …/documents/{document_id}/decisions` body states. Raises
    `DecisionRequestError` for a body of the wrong shape; whether the decision itself may be
    made, such as whether it needs a reason, is the store's to say."""
    if not DOCUMENT_ID.fullmatch(document_id):
        raise DecisionRequestError("A document is named by its identifier, a UUIDv7.")
    if not isinstance(body, dict):
        raise DecisionRequestError("The body must be an object.")
    if extra := sorted(set(body) - DECISION_FIELDS):
        raise DecisionRequestError(
            f"A decision gives only {sorted(DECISION_FIELDS)}, not {extra}. "
            "It never names who decided."
        )
    version, digest, verdict = body.get("version"), body.get("digest"), body.get("decision")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise DecisionRequestError("`version` must be the version's number, from 1.")
    if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
        raise DecisionRequestError("`digest` must be the SHA-256 of the text shown, in hex.")
    if verdict not in (APPROVED, REJECTED):
        raise DecisionRequestError(f"`decision` must be {APPROVED!r} or {REJECTED!r}.")
    reason, edited_text = body.get("reason"), body.get("edited_text")
    if not (reason is None or isinstance(reason, str)):
        raise DecisionRequestError("`reason` must be text, or left out.")
    if not (edited_text is None or isinstance(edited_text, str)):
        raise DecisionRequestError("`edited_text` must be text, or left out.")
    stated: Verdict = APPROVED if verdict == APPROVED else REJECTED
    return Decision(document_id, version, digest, stated, reason, edited_text)


def parse_answers(document_id: str, body: object) -> tuple[int, list[DraftAnswer]]:
    """The version and answers a `POST …/documents/{document_id}/answers` body states. Raises
    `DecisionRequestError` for a body of the wrong shape; whether the answers may be recorded,
    such as whether the version asks those questions, is the store's to say."""
    if not DOCUMENT_ID.fullmatch(document_id):
        raise DecisionRequestError("A document is named by its identifier, a UUIDv7.")
    if not isinstance(body, dict):
        raise DecisionRequestError("The body must be an object.")
    if extra := sorted(set(body) - ANSWERS_FIELDS):
        raise DecisionRequestError(
            f"Answers give only {sorted(ANSWERS_FIELDS)}, not {extra}. "
            "They never name who answered."
        )
    version, given = body.get("version"), body.get("answers")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise DecisionRequestError("`version` must be the version's number, from 1.")
    if not isinstance(given, list) or not given:
        raise DecisionRequestError("`answers` must be a list of at least one answer.")
    answers = []
    for answer in given:
        if not isinstance(answer, dict) or set(answer) != ANSWER_FIELDS:
            raise DecisionRequestError(f"Each answer gives exactly {sorted(ANSWER_FIELDS)}.")
        question, text = answer["answered_question"], answer["answer_text"]
        if not isinstance(question, str) or not QUESTION_ID.fullmatch(question):
            raise DecisionRequestError("`answered_question` must be a question's identifier.")
        if not isinstance(text, str):
            raise DecisionRequestError("`answer_text` must be text.")
        answers.append(DraftAnswer(answered_question=question, answer_text=text))
    return version, answers


class NoDrafterError(ValueError):
    """A request for changes to a document no agent drafted, so none can revise it."""


def drafter(store: ProjectDocuments, project_id: str, document_id: str) -> tuple[str, str]:
    """The agent that drafted the latest version an agent drafted of `document_id`, and the
    document's kind: the agent asked to revise it as a person asks (docs/specs/drafting.md), so
    the app names none. Raises `NoDrafterError` if no agent drafted any version; a document the
    project does not hold is the store's to refuse."""
    for document in store.documents(project_id):
        if document["document_id"] != document_id:
            continue
        for version in reversed(document["versions"]):
            if version["drafted_by"] is not None:
                return version["drafted_by"]["agent_id"], document["document_kind"]
        raise NoDrafterError("No agent drafted this document, so none can revise it.")
    return "", ""


class StaleDraftRequestError(ValueError):
    """A request to draft a document again that names a document the project does not hold
    (`found` False) or a version that is not its latest, so nothing runs and nothing is
    recorded."""

    def __init__(self, detail: str, *, found: bool) -> None:
        super().__init__(detail)
        self.detail = detail
        self.found = found


def drafter_of_latest(
    store: ProjectDocuments, project_id: str, document_id: str, version: int
) -> tuple[str, str]:
    """The agent to draft `document_id` again and the document's kind, as `drafter` gives them,
    once `version` is checked to be the latest the project holds: a person asks for the next
    draft of what they were shown. Raises `StaleDraftRequestError` otherwise, and
    `NoDrafterError` if no agent drafted the document."""
    held = next((d for d in store.documents(project_id) if d["document_id"] == document_id), None)
    if held is None:
        raise StaleDraftRequestError("The project holds no such document.", found=False)
    latest = held["versions"][-1]["version"]
    if version != latest:
        raise StaleDraftRequestError(
            f"Version {version} is not the latest: version {latest} is.", found=True
        )
    return drafter(store, project_id, document_id)

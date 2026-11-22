"""What a person sends to change a document, checked in itself before it is checked against the
log: a decision on a version, and answers to the questions a version asks
(docs/specs/projects.md, invariants 12 and 13; docs/specs/drafting.md).

A change malformed in itself raises `ProjectError` and records nothing, not even a refusal. Only
a well-formed change that names anything but the document's latest text is refused against the
log (`dd_harness.projects.fold.check_latest`), and that refusal is recorded.
"""

from __future__ import annotations

import re
from typing import Any

from dd_harness.project_decision import Decision as Decision
from dd_harness.project_decision import Verdict as Verdict
from dd_harness.projects.fold import APPROVED, REJECTED
from dd_harness.projects.rules import DIGEST, PROJECT_ID, ProjectError
from dd_sdk.contract.models import QUESTION_ID_PATTERN, DraftAnswer

QUESTION_ID = re.compile(QUESTION_ID_PATTERN)
# The longest reason the harness keeps, in characters: room for a paragraph, not a document.
REASON_MAX_LENGTH = 2000
# The longest answer the harness keeps, in characters: a definition or a paragraph of methods.
ANSWER_MAX_LENGTH = 2000
# The longest change a person may ask of a version, in characters: a paragraph of instructions.
REQUEST_MAX_LENGTH = 2000


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


def check_names(document_id: str, digest: str) -> None:
    """Raises `ProjectError` for a change that names no well-formed document or digest. Such a
    change is malformed in itself, so it records nothing, not even a refusal."""
    if not PROJECT_ID.fullmatch(document_id):
        raise ProjectError("a document is named by its UUIDv7")
    if not DIGEST.fullmatch(digest):
        raise ProjectError("a digest is a SHA-256 in lower-case hex")


def check_decision(decision: Decision) -> None:
    """Raises `ProjectError` for a decision malformed in itself, which records nothing."""
    check_names(decision.document_id, decision.digest)
    if decision.verdict not in (APPROVED, REJECTED):
        raise ProjectError(f"a decision is {APPROVED!r} or {REJECTED!r}, not {decision.verdict!r}")
    edited = decision.edited_text is not None
    if edited and decision.verdict == REJECTED:
        raise ProjectError("an edited text can be approved, not rejected")
    reason = decision.stated_reason
    if reason is None and reason_required(decision.verdict, edited=edited):
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


def check_request(instruction: str) -> str:
    """The change a person asked for, stripped. Raises `ProjectError` for one malformed in
    itself, which records nothing: a blank or overlong request (docs/specs/drafting.md)."""
    text = instruction.strip()
    if not text:
        raise ProjectError("say what to change")
    if len(text) > REQUEST_MAX_LENGTH:
        raise ProjectError(f"a request for changes is at most {REQUEST_MAX_LENGTH} characters")
    return text

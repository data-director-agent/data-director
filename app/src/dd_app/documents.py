"""A project's documents as the shell draws them, and a person's decision as the harness takes it
(docs/specs/projects.md).

The harness decides and records (`dd_harness.projects`). The app reads back what the log holds,
together with the harness's rule for when a decision needs a reason, and passes a person's
decision on unchanged except for its shape. A decision request never names who decided: the
server gives the store the principal its authenticator names.
"""

from __future__ import annotations

import re
from typing import Any

from dd_harness.projects import (
    APPROVED,
    REJECTED,
    Decision,
    ProjectStore,
    Verdict,
    review_rules,
)

DIGEST = re.compile(r"[0-9a-f]{64}")
# What a decision request may give; anything else, such as a decider, is refused.
DECISION_FIELDS = frozenset({"version", "digest", "decision", "reason", "edited_text"})


class DecisionRequestError(ValueError):
    """A decision request the shell should never send: malformed, so nothing is recorded."""


def view(store: ProjectStore, project_id: str) -> dict[str, Any]:
    """`GET /api/projects/{id}/documents`: each document with every version and its state, and
    the rule a decision form states. Raises `UnknownProjectError` for an unknown project."""
    return {
        "project_id": project_id,
        "documents": store.documents(project_id),
        "review": review_rules(),
    }


def parse_decision(document_id: str, body: object) -> Decision:
    """The decision a `POST …/documents/{document_id}/decisions` body states. Raises
    `DecisionRequestError` for a body of the wrong shape; whether the decision itself may be
    made, such as whether it needs a reason, is the store's to say."""
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

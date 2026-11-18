"""Hypothesis strategies for sequences of changes to a project's documents, as the project rules
write them, for `dd_harness.testing.check_a_log_replays_as_it_folds`. Shared by the file
backend's tests (`test_storage.py`) and the PostgreSQL backend's (`test_postgres.py`)."""

from __future__ import annotations

from typing import Any

from hypothesis import strategies as st

from dd_sdk.contract.models import DocumentKind

# Any text that encodes as UTF-8, as a version's text must.
texts = st.text(max_size=24)
question_ids = st.sampled_from([f"q-{n:016x}" for n in range(4)])
# Events the fold reads past.
others = st.fixed_dictionaries(
    {
        "event": st.sampled_from(["conversation_started", "project_renamed", "inventory_added"]),
        "note": texts,
    }
)


def _version_added(draw: st.DrawFn, kind: str, document_id: str, version: int) -> dict[str, Any]:
    change: dict[str, Any] = {
        "event": "document_version_added",
        "document_id": document_id,
        "document_kind": kind,
        "version": version,
        "text": draw(texts),
        "media_type": draw(st.sampled_from(["text/markdown", "application/ld+json"])),
        "questions": [
            {"question_id": q, "question_prompt": draw(texts)}
            for q in draw(st.lists(question_ids, max_size=2, unique=True))
        ],
    }
    if draw(st.booleans()):
        change["document_title"] = draw(texts)
    if version > 1 and draw(st.booleans()):
        change["revises"] = version - 1
    return change


def _decided_or_answered(draw: st.DrawFn, document_id: str, versions: int) -> dict[str, Any]:
    """A decision on, or an answer to a question of, one of a document's versions."""
    named = {"document_id": document_id, "version": draw(st.integers(1, versions))}
    if draw(st.booleans()):
        decided = {"event": "document_version_decided", **named}
        decided["decision"] = draw(st.sampled_from(["approved", "rejected"]))
        if draw(st.booleans()):
            decided["reason"] = draw(texts)
        return decided
    return {
        "event": "document_question_answered",
        **named,
        "question_id": draw(question_ids),
        "answer_text": draw(texts),
    }


@st.composite
def document_changes(draw: st.DrawFn, max_changes: int = 12) -> list[dict[str, Any]]:
    """Changes to a project's documents in an order the rules could write them: a version is
    decided or answered only once added, versions are numbered from 1, and a document keeps its
    kind."""
    kinds: dict[str, str] = {}
    versions: dict[str, int] = {}
    changes: list[dict[str, Any]] = []
    for _ in range(draw(st.integers(0, max_changes))):
        action = draw(st.sampled_from(["add", "decide or answer", "other"]))
        if action == "other":
            changes.append(draw(others))
        elif action == "add" or not versions:
            document_id = draw(st.sampled_from([*versions, f"doc-{len(versions)}"]))
            kind = kinds.setdefault(document_id, draw(st.sampled_from(list(DocumentKind))).value)
            versions[document_id] = versions.get(document_id, 0) + 1
            changes.append(_version_added(draw, kind, document_id, versions[document_id]))
        else:
            document_id = draw(st.sampled_from(list(versions)))
            changes.append(_decided_or_answered(draw, document_id, versions[document_id]))
    return changes

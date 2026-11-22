"""A project log holding every event type, for checking a project's provenance graph
(docs/specs/provenance.md, Completeness and validation).

`every_event` stamps one or more events of each type the log can hold, with the fields the
project rules write, oldest first. Events a run caused name `run`, so a test can store that run
and find it linked. A value `"@<event type>"` names the first earlier event of that type by its
`event_id`, as a decision names its proposal and an escalation's move names its opening.
`EventLog` holds such a list as a `ProjectRecord`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from dd_harness.testing.fixtures import TEST_PRINCIPAL
from dd_sdk.contract.models import Principal, new_invocation_id

MEMBER = "https://orcid.org/0000-0002-1694-233X"
TEAM = "research-data-team"


def digest(label: str) -> str:
    """A SHA-256 digest standing in for content the log names."""
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _changes(
    run: str, agent_id: str, document_id: str, conversation_id: str
) -> list[dict[str, Any]]:
    by_run = {"caused_by": run}
    fact = {"fact_kind": "funder", "fact_subject": "project", "fact_funder_name": "UKRI"}
    version = {"document_id": document_id, "document_kind": "readme", "media_type": "text/markdown"}
    escalation = {"escalation_id": "@escalation_opened"}
    deposit = {
        "digest": digest("package"),
        "format": "ro-crate",
        "item_digest": digest("item"),
        "item_format": "zip",
        "repository_id": "r3d100000001",
        "repository_name": "A repository",
        "transport": "zenodo",
        "base_url": "https://sandbox.zenodo.org",
        "sandbox": True,
    }
    return [
        {"event": "conversation_started", "conversation_id": conversation_id},
        {
            "event": "project_renamed",
            "title": "Moorland sensors",
            "title_source": "model",
            **by_run,
        },
        {"event": "entry_chosen", "entry": 2, "entry_source": "model", **by_run},
        {"event": "step_marked", "step_id": "plan.write", "mark": "done"},
        {"event": "intake_answered", "question_id": "q-data", "answer_values": ["yes"]},
        {"event": "intake_dismissed"},
        {
            "event": "inventory_added",
            "digest": digest("inventory"),
            "canonicalisation": "dd-input-json-v1",
            "file_count": 2,
            "inventory_made_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "event": "documentation_added",
            "name": "notes.md",
            "media_type": "text/markdown",
            "size": 10,
            "digest": digest("notes"),
        },
        {
            "event": "researcher_added",
            "orcid_id": TEST_PRINCIPAL.principal_id,
            "digest": digest("orcid record"),
            "canonicalisation": "dd-input-json-v1",
            "record_retrieved_at": "2026-01-01T00:00:00+00:00",
        },
        {"event": "researcher_withdrawn", "orcid_id": TEST_PRINCIPAL.principal_id},
        {"event": "member_added", "member_id": MEMBER, "role": "contributor"},
        {"event": "member_role_changed", "member_id": MEMBER, "role": "owner"},
        {"event": "member_removed", "member_id": MEMBER},
        {
            "event": "repository_chosen",
            "repository_id": "r3d100000001",
            "re3data_id": "r3d100000001",
            "repository_name": "A repository",
            "record_hash": digest("re3data record"),
            "requirement_sets": [{"ref": "core", "sha256": digest("core set")}],
            "digest": digest("requirements"),
        },
        {
            "event": "document_version_added",
            **version,
            "version": 1,
            "digest": digest("draft"),
            "drafted_by": {
                "agent_id": agent_id,
                "agent_version": "0",
                "invocation_id": run,
                "document_derivation": "model",
            },
            **by_run,
        },
        {
            "event": "document_question_answered",
            "document_id": document_id,
            "version": 1,
            "question_id": "q-0123456789abcdef",
            "answer_text": "CC BY 4.0",
        },
        {
            "event": "document_version_decided",
            "document_id": document_id,
            "version": 1,
            "digest": digest("draft"),
            "decision": "rejected",
            "reason": "Name the licence.",
        },
        {
            "event": "document_revision_requested",
            "document_id": document_id,
            "version": 1,
            "digest": digest("draft"),
            "instruction": "Name the licence.",
        },
        {
            "event": "document_change_refused",
            "refusal": "not-latest-version",
            "document_id": document_id,
            "version": 1,
            "latest_version": 2,
        },
        {
            "event": "document_version_added",
            **version,
            "version": 2,
            "digest": digest("edited"),
            "revises": {"document_id": document_id, "version": 1},
        },
        {
            "event": "document_version_decided",
            "document_id": document_id,
            "version": 2,
            "digest": digest("edited"),
            "decision": "approved",
        },
        {"event": "fact_proposed", "agent_id": agent_id, "fact": fact, **by_run},
        {
            "event": "fact_decided",
            "verdict": "confirmed",
            "fact": fact,
            "proposal": "@fact_proposed",
        },
        {"event": "fact_decided", "verdict": "rejected", "fact": fact, "reason": "Not funded."},
        {
            "event": "project_validated",
            "digest": digest("report"),
            "canonicalisation": "dd-input-json-v1",
            "conforms": True,
            "requirements_digest": digest("requirements"),
        },
        {
            "event": "deposit_item_decided",
            "item_id": "file:data/a.csv",
            "item": {"source": "inventory", "kind": "file", "path": "data/a.csv", "question": "?"},
            "decision": "keep",
            "inventory_digest": digest("inventory"),
        },
        {
            "event": "deposit_checks_confirmed",
            "statements": [{"id": "consent", "text": "Consent covers sharing."}],
            "inventory_digest": digest("inventory"),
        },
        {
            "event": "package_built",
            "format": "ro-crate",
            "digest": digest("package"),
            "report_digest": digest("report"),
            "requirements_digest": digest("requirements"),
            "documents": [{"document_id": document_id, "document_kind": "readme", "version": 2}],
            "runs": [run],
        },
        {"event": "deposit_approved", **deposit},
        {
            "event": "deposit_recorded",
            "approval": "@deposit_approved",
            **deposit,
            "deposit_id": "123",
            "draft_url": "https://sandbox.zenodo.org/deposit/123",
            "unplaced": [],
        },
        {
            "event": "deposit_failed",
            "approval": "@deposit_approved",
            **deposit,
            "status": 503,
            "reason": "Unavailable.",
        },
        {"event": "support_team_chosen", "team_id": TEAM},
        {
            "event": "escalation_opened",
            "team_id": TEAM,
            "origin": {"kind": "agent", "invocation_id": run, "agent_id": agent_id},
            "note": "Please check the licence.",
            "scope_shared": ["documents"],
        },
        {"event": "escalation_taken", **escalation, "acting_as": "steward"},
        {"event": "escalation_released", **escalation, "acting_as": "steward"},
        {"event": "escalation_waiting", **escalation, "acting_as": "steward"},
        {"event": "escalation_replied", **escalation, "note": "Use CC BY.", "acting_as": "steward"},
        {"event": "escalation_handed_back", **escalation, "acting_as": "steward"},
        {"event": "escalation_resolved", **escalation, "acting_as": "steward"},
        {"event": "escalation_reopened", **escalation},
        {"event": "escalation_withdrawn", **escalation},
        {"event": "conversation_deleted", "conversation_id": conversation_id},
        {"event": "conversation_restored", "conversation_id": conversation_id},
        {"event": "project_deleted"},
        {"event": "project_restored"},
    ]


def every_event(
    project_id: str,
    run: str,
    *,
    agent_id: str = "stub.document",
    conversation_id: str | None = None,
    acted_for: Principal = TEST_PRINCIPAL,
) -> list[dict[str, Any]]:
    """A project's log holding every event type, oldest first, each a second after the last."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    document_id = new_invocation_id()
    changes = _changes(run, agent_id, document_id, conversation_id or new_invocation_id())
    events: list[dict[str, Any]] = []
    for n, change in enumerate([{"event": "project_created", "title": "Sensors"}, *changes]):
        event = {
            "event_id": new_invocation_id(),
            "project_id": project_id,
            "at": (start + timedelta(seconds=n)).isoformat(),
            "acted_for": acted_for.model_dump(mode="json", exclude_none=True),
            "caused_by": "test",
            **change,
        }
        events.append({key: _named(value, events) for key, value in event.items()})
    return events


def _named(value: Any, earlier: Sequence[Mapping[str, Any]]) -> Any:
    if isinstance(value, str) and value.startswith("@"):
        return next(e["event_id"] for e in earlier if e["event"] == value[1:])
    return value


class EventLog:
    """A `ProjectRecord` over events held in memory."""

    def __init__(self, events: Sequence[Mapping[str, Any]]) -> None:
        self._events = [dict(e) for e in events]

    def exists(self, project_id: str) -> bool:
        return any(e["project_id"] == project_id for e in self._events)

    def events(self, project_id: str) -> list[dict[str, Any]]:
        return [dict(e) for e in self._events if e["project_id"] == project_id]

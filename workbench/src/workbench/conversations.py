"""Conversations, derived from the invocation store (ADR-0012).

A conversation is the set of top-level invocations sharing a `conversation_id`. There is no
conversation store: each turn is an ordinary invocation, so everything here is read back from
`invocations.jsonl` and the per-run `request.json`. Turn order is file order, which is the order
the conductor finished the turns in. A child invocation (one with `parent_invocation_id`) is not a
turn; it is listed under the turn that delegated it.

`history` is the conversation as a `Message.history` list, so a caller can send the next turn
without rebuilding it. `version_changes` marks where an agent's version differs from the version
that agent had earlier in the same conversation, which is what a developer needs to see when an
agent is rebuilt mid-conversation.

TODO: this scans the whole JSONL file on every call. Add an index if the store grows large.
"""

from __future__ import annotations

import json
from typing import Any

from dd_sdk.contract.models import ConversationTurn, TurnRole, to_document
from workbench.store import RunStore


def list_conversations(store: RunStore) -> list[dict[str, Any]]:
    """One summary per conversation, most recently active first."""
    summaries: dict[str, dict[str, Any]] = {}
    for envelope in store.iter_envelopes():
        conversation_id = envelope.get("conversation_id")
        if not conversation_id or envelope.get("parent_invocation_id"):
            continue
        summary = summaries.get(conversation_id)
        if summary is None:
            summary = summaries[conversation_id] = {
                "conversation_id": conversation_id,
                "agent_id": envelope["agent_id"],
                "turns": 0,
                "started_at": envelope["completed_at"],
            }
        summary["turns"] += 1
        summary["last_completed_at"] = envelope["completed_at"]
        summary["last_status"] = envelope["outcome"]["status"]
    return sorted(summaries.values(), key=lambda s: str(s["last_completed_at"]), reverse=True)


def get_conversation(store: RunStore, conversation_id: str) -> dict[str, Any] | None:
    """Every turn of one conversation, with its children, version changes and history.

    None if no invocation carries `conversation_id`.
    """
    top: list[dict[str, Any]] = []
    children: dict[str, list[dict[str, Any]]] = {}
    for envelope in store.iter_envelopes():
        if envelope.get("conversation_id") != conversation_id:
            continue
        parent = envelope.get("parent_invocation_id")
        if parent:
            children.setdefault(parent, []).append(envelope)
        else:
            top.append(envelope)
    if not top and not children:
        return None

    turns: list[dict[str, Any]] = []
    for index, envelope in enumerate(top):
        request = store.get_request(envelope["invocation_id"]) or {}
        turns.append(
            {
                "turn_index": index,
                "invocation_id": envelope["invocation_id"],
                "agent_id": envelope["agent_id"],
                "agent_version": envelope["agent_version"],
                "status": envelope["outcome"]["status"],
                "completed_at": envelope["completed_at"],
                "input": request.get("input"),
                "envelope": envelope,
                "children": children.get(envelope["invocation_id"], []),
            }
        )
    return {
        "conversation_id": conversation_id,
        "turns": turns,
        "version_changes": version_changes(turns),
        "history": [to_document(t) for t in history(turns)],
    }


def version_changes(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Where an agent's version differs from its version earlier in the conversation.

    Children count as well as turns, so an orchestrator's sub-agent being rebuilt is reported.
    """
    seen: dict[str, str] = {}
    changes: list[dict[str, Any]] = []
    for turn in turns:
        for envelope in [*turn["children"], turn["envelope"]]:
            agent_id, version = envelope["agent_id"], envelope["agent_version"]
            before = seen.get(agent_id)
            if before is not None and before != version:
                changes.append(
                    {
                        "turn_index": turn["turn_index"],
                        "agent_id": agent_id,
                        "from": before,
                        "to": version,
                    }
                )
            seen[agent_id] = version
    return changes


def history(turns: list[dict[str, Any]]) -> list[ConversationTurn]:
    """The conversation so far as `Message.history`: each turn's input, then the agent's reply.

    A `Message` turn contributes its text; any other input contributes its JSON, so a structured
    turn is still visible to a conversational agent. An agent turn is the reply text if the
    payload is a `Reply`, otherwise the outcome statement.
    """
    out: list[ConversationTurn] = []
    for turn in turns:
        document = turn["input"] or {}
        if document.get("schema_class") == "Message":
            text = str(document.get("message_text", ""))
        else:
            text = json.dumps(document, sort_keys=True, separators=(",", ":"))
        out.append(ConversationTurn(role=TurnRole.USER, turn_text=text))
        envelope = turn["envelope"]
        payload = envelope.get("payload") or {}
        reply = payload.get("reply_text") if payload.get("schema_class") == "Reply" else None
        out.append(
            ConversationTurn(
                role=TurnRole.AGENT,
                turn_text=str(reply or envelope["outcome"]["statement"]),
                turn_agent_id=envelope["agent_id"],
                turn_agent_version=envelope["agent_version"],
                turn_invocation_id=envelope["invocation_id"],
            )
        )
    return out

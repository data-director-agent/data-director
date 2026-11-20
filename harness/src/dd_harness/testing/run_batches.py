"""The conformance check for `RunStorage.get_many`, which `check_run_storage` runs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from dd_harness.storage import RunStorage
from dd_sdk.contract.models import new_invocation_id


def _envelope() -> dict[str, Any]:
    """The fields a backend might index, as `dd_harness.testing.storage.stored_envelope` has."""
    return {
        "invocation_id": new_invocation_id(),
        "agent_id": "stub.storage",
        "agent_version": "0.1.0",
        "conversation_id": None,
        "parent_invocation_id": None,
        "project_id": None,
        "completed_at": datetime.now(UTC).isoformat(),
        "outcome": {"status": "succeeded", "statement": "Stored for a storage check."},
    }


def check_runs_are_read_many_at_once(make: Callable[[str], RunStorage]) -> None:
    store = make("runs")
    envelope, absent = _envelope(), _envelope()
    request = {"agent_id": "stub.storage", "input": {"n": 1}}
    store.append(envelope, request)
    named = [envelope["invocation_id"], absent["invocation_id"], "../escape"]
    # A run not stored, or named by a malformed identifier, is left out.
    assert store.get_many(named) == {envelope["invocation_id"]: envelope}
    assert store.get_many(named, "request") == {envelope["invocation_id"]: request}
    assert store.get_many([]) == {}


RUN_BATCH_CHECKS: dict[str, Callable[[Callable[[str], RunStorage]], None]] = {
    "runs are read many at once": check_runs_are_read_many_at_once,
}

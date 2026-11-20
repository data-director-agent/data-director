"""The conformance check for `RunStorage.get_many`, which `check_run_storage` runs."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dd_harness.testing.storage import MakeRunStorage


def check_runs_are_read_many_at_once(make: MakeRunStorage) -> None:
    from dd_harness.testing.storage import stored_envelope

    store = make("runs")
    envelope, absent = stored_envelope(), stored_envelope()
    request = {"agent_id": "stub.storage", "input": {"n": 1}}
    store.append(envelope, request)
    named = [envelope["invocation_id"], absent["invocation_id"], "../escape"]
    # A run not stored, or named by a malformed identifier, is left out.
    assert store.get_many(named) == {envelope["invocation_id"]: envelope}
    assert store.get_many(named, "request") == {envelope["invocation_id"]: request}
    assert store.get_many([]) == {}


RUN_BATCH_CHECKS: dict[str, Callable[[MakeRunStorage], None]] = {
    "runs are read many at once": check_runs_are_read_many_at_once,
}

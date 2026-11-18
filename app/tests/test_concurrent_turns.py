"""Two app processes over one store run one turn of a conversation at a time (#983): the turn
lock is the store's, not the process's (docs/specs/app.md, "Turn locks")."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

import pytest
from support import configure_env, delegating_app, dist_dir

from dd_app.governance import Governance, TurnConflictError
from dd_app.turn_body import Turn
from dd_app.turn_lock import hold_turn
from dd_harness.projects import ProjectStore
from dd_harness.settings import conversation_locks
from dd_harness.testing import TEST_PRINCIPAL
from dd_harness.turn_locks import LocalConversationLocks, Release
from dd_sdk.contract.models import Envelope, InvocationRequest


def an_app(env: Path, dist: Path) -> Governance:
    """An app over the shared runs and projects at `env`, with the locks `Governance.create`
    opens beside the runs."""
    governance, _app = delegating_app(env, dist, ProjectStore(env / "projects"))
    governance.turn_locks = conversation_locks(env)
    return governance


def test_apps_over_one_store_run_one_turn_of_a_conversation_at_a_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = configure_env(monkeypatch, tmp_path)
    dist = dist_dir(tmp_path)
    first, second = an_app(env, dist), an_app(env, dist)
    entered, release = threading.Event(), threading.Event()
    invoke = first.conductor.invoke

    def held(request: InvocationRequest, **kwargs: Any) -> Any:
        entered.set()
        release.wait(timeout=30)
        return invoke(request, **kwargs)

    first.conductor.invoke = held  # type: ignore[method-assign]
    conversation_id = first.start_conversation(TEST_PRINCIPAL)
    hello = Turn("orchestrator.stub", "hello world", None)

    async def scenario() -> tuple[Envelope, Envelope]:
        running = asyncio.create_task(first.turn(conversation_id, hello, TEST_PRINCIPAL))
        await asyncio.to_thread(entered.wait, 30)
        with pytest.raises(TurnConflictError):
            await second.turn(conversation_id, hello, TEST_PRINCIPAL)
        release.set()
        answered = await running
        follows = Turn("orchestrator.stub", "hello again", answered.invocation_id)
        return answered, await second.turn(conversation_id, follows, TEST_PRINCIPAL)

    try:
        answered, again = asyncio.run(scenario())
    finally:
        release.set()
        first.conductor.close()
        second.conductor.close()

    turns = [
        e
        for e in second.conductor.store.iter_envelopes(conversation_id=conversation_id)
        if not e.get("parent_invocation_id")
    ]
    assert [e["invocation_id"] for e in turns] == [answered.invocation_id, again.invocation_id]
    shown = (second.conductor.store.get_request(again.invocation_id) or {})["input"]
    user, _agent = shown["history"]
    assert user["turn_text"] == "hello world"


def test_a_turn_cancelled_while_taking_the_lock_releases_it() -> None:
    """A request that goes away while its lock is being taken leaves the conversation free."""
    local = LocalConversationLocks()
    entered, proceed, taken = threading.Event(), threading.Event(), threading.Event()

    class Slow:
        def try_hold(self, conversation_id: str) -> Release | None:
            entered.set()
            proceed.wait(timeout=30)
            release = local.try_hold(conversation_id)
            taken.set()
            return release

    async def scenario() -> None:
        taking = asyncio.create_task(hold_turn(Slow(), "conversation-a"))
        await asyncio.to_thread(entered.wait, 30)
        taking.cancel()
        with pytest.raises(asyncio.CancelledError):
            await taking
        proceed.set()
        await asyncio.to_thread(taken.wait, 30)
        for _ in range(100):  # the thread finishes taking the lock, then gives it back
            if not local.held():
                return
            await asyncio.sleep(0.01)

    try:
        asyncio.run(scenario())
    finally:
        proceed.set()
    assert local.held() == frozenset()

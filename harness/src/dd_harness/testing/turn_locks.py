"""Conformance checks for a `ConversationLocks` backend (`dd_harness.turn_locks`,
docs/specs/storage.md, "Turn locks").

Each check takes `make(name)`, which opens a locks instance; the same name opens another instance
over the same location, as a second app process over one store would. Conversation ids are fresh
in every check, because a backend's locks may be shared more widely than its location (PostgreSQL
advisory locks belong to the whole database).
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

from dd_harness.turn_locks import ConversationLocks

type MakeConversationLocks = Callable[[str], ConversationLocks]


def _conversation() -> str:
    return f"conversation-{uuid.uuid4()}"


def check_one_holder_per_conversation(make: MakeConversationLocks) -> None:
    """While one instance holds a conversation's lock, another over the same location is refused
    at once, and so is the holder itself (guarantee 1)."""
    first, second = make("locks"), make("locks")
    conversation_id = _conversation()
    release = first.try_hold(conversation_id)
    assert release is not None, "a lock nobody holds was refused"
    try:
        assert second.try_hold(conversation_id) is None, "two instances held one conversation"
        assert first.try_hold(conversation_id) is None, "one instance held a conversation twice"
    finally:
        release()


def check_conversations_are_independent(make: MakeConversationLocks) -> None:
    """Holding one conversation's lock holds no other's (guarantee 2)."""
    first, second = make("locks"), make("locks")
    held = first.try_hold(_conversation())
    assert held is not None
    try:
        other = second.try_hold(_conversation())
        assert other is not None, "holding one conversation held another"
        other()
    finally:
        held()


def check_a_released_lock_may_be_held_again(make: MakeConversationLocks) -> None:
    """Once released, through either instance, a lock may be held by the other; releasing twice
    changes nothing (guarantee 3)."""
    first, second = make("locks"), make("locks")
    conversation_id = _conversation()
    release = first.try_hold(conversation_id)
    assert release is not None
    release()
    release()  # a second release does nothing
    again = second.try_hold(conversation_id)
    assert again is not None, "a released lock could not be held again"
    try:
        assert first.try_hold(conversation_id) is None, "a second release freed the new holder"
    finally:
        again()


def check_one_of_many_racing_holders_wins(make: MakeConversationLocks) -> None:
    """Threads racing for one conversation through several instances: exactly one holds it
    (guarantee 1, under contention)."""
    racers = 8
    instances = [make("locks") for _ in range(2)]
    conversation_id = _conversation()
    start = threading.Barrier(racers)
    won: list[Callable[[], None]] = []
    guard = threading.Lock()

    def race(locks: ConversationLocks) -> None:
        start.wait()
        release = locks.try_hold(conversation_id)
        if release is not None:
            with guard:
                won.append(release)

    threads = [threading.Thread(target=race, args=(instances[n % 2],)) for n in range(racers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    try:
        assert len(won) == 1, f"{len(won)} racers held one conversation"
    finally:
        for release in won:
            release()


CONVERSATION_LOCK_CHECKS: dict[str, Callable[[MakeConversationLocks], None]] = {
    "one holder per conversation": check_one_holder_per_conversation,
    "conversations are independent": check_conversations_are_independent,
    "a released lock may be held again": check_a_released_lock_may_be_held_again,
    "one of many racing holders wins": check_one_of_many_racing_holders_wins,
}


def check_conversation_locks(make: MakeConversationLocks) -> None:
    """Every `ConversationLocks` check."""
    for check in CONVERSATION_LOCK_CHECKS.values():
        check(make)

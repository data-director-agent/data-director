"""Taking a conversation's turn lock from the app's event loop (docs/specs/app.md, "Turn locks").

The lock is the run store's (`dd_harness.turn_locks`), taken in a thread because a backend may
open a file or a database connection to take it.
"""

from __future__ import annotations

import asyncio

from dd_harness.turn_locks import ConversationLocks, Release


async def hold_turn(locks: ConversationLocks, conversation_id: str) -> Release | None:
    """The conversation's turn lock, as `ConversationLocks.try_hold` gives it. A turn cancelled
    while the lock is being taken releases what it took, so the conversation is not left
    refused."""
    holding = asyncio.ensure_future(asyncio.to_thread(locks.try_hold, conversation_id))
    try:
        return await asyncio.shield(holding)
    except asyncio.CancelledError:
        holding.add_done_callback(_release_taken)
        raise


def _release_taken(holding: asyncio.Future[Release | None]) -> None:
    """Release the lock a cancelled turn took, if it took one."""
    if not holding.cancelled() and holding.exception() is None and (release := holding.result()):
        release()

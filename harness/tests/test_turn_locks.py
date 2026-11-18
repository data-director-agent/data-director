"""Each conversation's turn lock, on files and in one process (docs/specs/storage.md, "Turn
locks"). The PostgreSQL backend passes the same checks in `test_postgres.py`."""

from __future__ import annotations

import multiprocessing
from collections.abc import Callable
from pathlib import Path

import pytest

from dd_harness.settings import conversation_locks
from dd_harness.testing import CONVERSATION_LOCK_CHECKS
from dd_harness.turn_locks import (
    LOCKS_DIR,
    ConversationLocks,
    FileConversationLocks,
    LocalConversationLocks,
)

type Check = Callable[[Callable[[str], ConversationLocks]], None]


@pytest.mark.parametrize("check", CONVERSATION_LOCK_CHECKS.values(), ids=CONVERSATION_LOCK_CHECKS)
def test_file_locks_keep_each_guarantee(tmp_path: Path, check: Check) -> None:
    check(lambda name: FileConversationLocks(tmp_path / name))


@pytest.mark.parametrize("check", CONVERSATION_LOCK_CHECKS.values(), ids=CONVERSATION_LOCK_CHECKS)
def test_local_locks_keep_each_guarantee_within_one_instance(check: Check) -> None:
    opened: dict[str, LocalConversationLocks] = {}
    check(lambda name: opened.setdefault(name, LocalConversationLocks()))


def test_a_conversation_id_never_names_a_file(tmp_path: Path) -> None:
    locks = FileConversationLocks(tmp_path)
    release = locks.try_hold("../../escape")
    assert release is not None
    release()
    (lock,) = (tmp_path / LOCKS_DIR).iterdir()
    assert lock.parent == tmp_path / LOCKS_DIR
    assert "escape" not in lock.name
    assert list(tmp_path.iterdir()) == [tmp_path / LOCKS_DIR]


def _hold_in_another_process(root: str, conversation_id: str) -> bool:
    """Whether another process can hold the conversation's lock."""
    release = FileConversationLocks(Path(root)).try_hold(conversation_id)
    if release is None:
        return False
    release()
    return True


def _hold_and_exit(root: str, conversation_id: str) -> None:
    """Hold the conversation's lock and end without releasing it, as a crashed app would."""
    assert FileConversationLocks(Path(root)).try_hold(conversation_id) is not None


def test_a_file_lock_holds_across_processes(tmp_path: Path) -> None:
    locks = FileConversationLocks(tmp_path)
    context = multiprocessing.get_context("spawn")
    release = locks.try_hold("conversation-a")
    assert release is not None
    with context.Pool(1) as pool:
        assert pool.apply(_hold_in_another_process, (str(tmp_path), "conversation-a")) is False
        assert pool.apply(_hold_in_another_process, (str(tmp_path), "conversation-b")) is True
        release()
        assert pool.apply(_hold_in_another_process, (str(tmp_path), "conversation-a")) is True


def test_a_file_lock_ends_with_the_process_that_held_it(tmp_path: Path) -> None:
    holder = multiprocessing.get_context("spawn").Process(
        target=_hold_and_exit, args=(str(tmp_path), "conversation-a")
    )
    holder.start()
    holder.join(timeout=60)
    assert holder.exitcode == 0
    assert FileConversationLocks(tmp_path).try_hold("conversation-a") is not None


def test_the_locks_are_opened_beside_the_runs(tmp_path: Path) -> None:
    locks = conversation_locks(tmp_path / "runs")
    assert isinstance(locks, FileConversationLocks)
    assert (tmp_path / "runs" / LOCKS_DIR).is_dir()

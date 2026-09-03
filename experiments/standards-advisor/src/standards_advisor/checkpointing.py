"""Checkpointer selection.

SQLite on disk for a real run, in memory for a test. §5's "each stage saves its result" comes
free from the checkpointer, and `durability="sync"` at invoke time means a boundary is on disk
before the next node starts.

The checkpoint database is working memory, not the audit trail — it is gitignored, prunable, and
its format belongs to a dependency. See `provenance/run_dir.py` for why the two coexist.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


@contextmanager
def checkpointer(path: Path | None) -> Iterator[BaseCheckpointSaver[Any]]:
    """Yield a checkpointer, closing it on the way out.

    `path` of `None` gives an in-memory saver — used by tests, and by `--no-checkpoints`.
    """
    if path is None:
        from langgraph.checkpoint.memory import InMemorySaver

        yield InMemorySaver()
        return

    from langgraph.checkpoint.sqlite import SqliteSaver

    with SqliteSaver.from_conn_string(str(path)) as saver:
        yield saver

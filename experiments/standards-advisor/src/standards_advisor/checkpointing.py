"""Checkpointer selection.

SQLite on disk for a real run, in memory for a test. §5's "each stage saves its result" comes
free from the checkpointer, and `durability="sync"` at invoke time means a boundary is on disk
before the next node starts.

The checkpoint database is working memory, not the audit trail — it is gitignored, prunable, and
its format belongs to a dependency. See `provenance/run_dir.py` for why the two coexist.

§8 changed what a checkpoint is *for*. It used to be a resume capability nothing used: every run
started and finished in one process, and the checkpoints were written for the audit property and
never read back. A pre-collection run pauses for a human, so the checkpoint is now written by one
process and read by another, and the round trip has to actually work. That is why the serialiser
below is pinned rather than left at its default.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.checkpoint.serde.base import SerializerProtocol


def state_types() -> list[type]:
    """Every type of ours that may legitimately come back out of a checkpoint.

    Derived from the `models` package rather than listed by hand, so a model added later is
    covered without anyone remembering to come here — but still scoped to our own document
    types, which is the point. It is deliberately not `True` (allow anything): the serialiser's
    own documentation warns that an attacker who can write to the checkpoint database may be able
    to trigger code execution when it is deserialised, and "only our own models" is a boundary
    worth stating even for a local prototype.
    """
    from standards_advisor.models import (
        candidates,
        common,
        elicitation,
        inputs,
        profile,
        provenance,
        recommendations,
    )

    modules = (
        candidates,
        common,
        elicitation,
        inputs,
        profile,
        provenance,
        recommendations,
    )
    found: list[type] = []
    for module in modules:
        for value in vars(module).values():
            if not isinstance(value, type) or value.__module__ != module.__name__:
                continue
            if issubclass(value, BaseModel | Enum):
                found.append(value)
    return found


def serializer() -> SerializerProtocol:
    """The checkpoint serialiser, with our own model types explicitly allowed.

    Without this, LangGraph permits any type through with a log warning that says it "will be
    blocked in a future version" — which would turn a resumable paused run into an unresumable
    one on a dependency upgrade, silently, since nothing in the test suite would notice until a
    run actually paused.
    """
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    return JsonPlusSerializer(allowed_msgpack_modules=state_types())


@contextmanager
def checkpointer(path: Path | None) -> Iterator[BaseCheckpointSaver[Any]]:
    """Yield a checkpointer, closing it on the way out.

    `path` of `None` gives an in-memory saver — used by tests, and by `--no-checkpoints`. Note
    that an in-memory saver cannot outlive the process, so a run that pauses under it can never
    be resumed; `runner.run_pipeline` refuses that combination up front rather than letting a
    researcher answer questions into a run that cannot continue.
    """
    if path is None:
        from langgraph.checkpoint.memory import InMemorySaver

        yield InMemorySaver(serde=serializer())
        return

    from langgraph.checkpoint.sqlite import SqliteSaver

    # `SqliteSaver.from_conn_string` takes no serialiser, so the connection is opened here
    # instead. `check_same_thread=False` matches what that helper does.
    with closing(sqlite3.connect(str(path), check_same_thread=False)) as connection:
        yield SqliteSaver(connection, serde=serializer())

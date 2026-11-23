"""What a case holds: the runs of one run, conversation or project, and the project they belong to
(docs/specs/casefile.md, Selection)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from dd_harness.project_log import ProjectLog
from dd_harness.provenance_graph import project_runs
from dd_harness.storage import RunStorage

SCOPES = ("run", "conversation", "project")


@dataclass(frozen=True)
class Selection:
    """The runs a case holds, each envelope as stored, in the order the runs were made (an
    `invocation_id` is a UUIDv7, so ordering by it orders by time), and the project whose log it
    holds, if any."""

    scope: str
    ident: str
    runs: tuple[Mapping[str, Any], ...]
    project_id: str | None


def _ordered(envelopes: Iterable[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    by_id = {e["invocation_id"]: e for e in envelopes}
    return tuple(by_id[i] for i in sorted(by_id))


def _descendants(
    root: Mapping[str, Any], pool: Iterable[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    """`root` and every run delegated from it, however deep."""
    children: dict[str, list[Mapping[str, Any]]] = {}
    for envelope in pool:
        parent = envelope.get("parent_invocation_id")
        if parent:
            children.setdefault(parent, []).append(envelope)
    found, todo = [root], [root]
    while todo:
        for child in children.get(todo.pop()["invocation_id"], []):
            found.append(child)
            todo.append(child)
    return found


def _run(runs: RunStorage, ident: str) -> Selection:
    root = runs.get(ident)
    if root is None:
        raise LookupError(f"no run {ident}")
    conversation = root.get("conversation_id")
    # A run outside any conversation is looked for among every run.
    pool = runs.iter_envelopes(conversation_id=conversation or None)
    return Selection("run", ident, _ordered(_descendants(root, pool)), None)


def _conversation(runs: RunStorage, log: ProjectLog | None, ident: str) -> Selection:
    turns = list(runs.iter_envelopes(conversation_id=ident))
    if not turns:
        raise LookupError(f"no conversation {ident}")
    project = log.project_of(ident) if log is not None else None
    return Selection("conversation", ident, _ordered(turns), project)


def _project(runs: RunStorage, log: ProjectLog | None, ident: str) -> Selection:
    if log is None or not log.exists(ident):
        raise LookupError(f"no project {ident}")
    stored = project_runs(log.events(ident), runs)
    return Selection("project", ident, _ordered(stored.values()), ident)


def select(runs: RunStorage, log: ProjectLog | None, scope: str, ident: str) -> Selection:
    """The runs, and project, a case of `scope` (`SCOPES`) holds for `ident`. `LookupError` if
    the stores hold no such run, conversation or project."""
    if scope == "run":
        return _run(runs, ident)
    if scope == "conversation":
        return _conversation(runs, log, ident)
    if scope == "project":
        return _project(runs, log, ident)
    raise ValueError(f"a case's scope is one of {', '.join(SCOPES)}, not {scope!r}")

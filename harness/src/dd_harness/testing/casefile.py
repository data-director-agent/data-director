"""`open_case`: a case for debugging, opened as the stores it is a copy of, so a reported failure
becomes a test (docs/specs/casefile.md)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dd_harness.casefile import case_root
from dd_harness.casefile.copy import PROJECTS, RUNS
from dd_harness.projects import ProjectStore
from dd_harness.store import RunStore


@contextmanager
def open_case(path: Path) -> Iterator[tuple[RunStore, ProjectStore | None]]:
    """The run store and project store of the case at `path`, a directory or a zip, for as long as
    the context lasts; no project store for a case that holds no project. A zip is unpacked into a
    temporary directory. Opening a case writes nothing to it."""
    with case_root(path) as root:
        projects = ProjectStore(root / PROJECTS) if (root / PROJECTS).is_dir() else None
        yield RunStore(root / RUNS), projects

"""`CountingLog`: a project log that counts what is asked of it, so that a test can show how many
reads a caller makes of the store, and that the number does not grow with the number of projects
(docs/specs/storage.md, "Listing")."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from dd_harness.project_log import ProjectLog


class CountingLog:
    """Passes every call to `log`, and counts each by the name of the method called. Each call
    is one read or change of the store; for the PostgreSQL backend, one query."""

    def __init__(self, log: ProjectLog) -> None:
        self._log = log
        self.calls: Counter[str] = Counter()

    def __getattr__(self, name: str) -> Any:
        found = getattr(self._log, name)
        if not callable(found):
            return found

        def counted(*args: Any, **kwargs: Any) -> Any:
            self.calls[name] += 1
            return found(*args, **kwargs)

        return counted

    def as_log(self) -> ProjectLog:
        """This, as the `ProjectLog` it stands in for."""
        return cast("ProjectLog", self)

    def total(self) -> int:
        """How many calls have been made of the log."""
        return sum(self.calls.values())

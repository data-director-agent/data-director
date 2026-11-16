"""What an agent that searches a registry needs to say about a search, whichever registry it is.

An agent defines its own retrieval protocol in front of each registry it reads (re3data,
FAIRsharing, ROR); these are the types those protocols share. A registry that cannot be asked
raises `RegistryUnavailable`, which the agent reports as `abstained(registry_unavailable)` or
answers from a snapshot marked stale. It is not the same as an empty result (R3.6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class RegistryUnavailable(Exception):
    """The registry could not be asked. Not the same as an empty result (R3.6)."""


@dataclass(frozen=True)
class Query:
    """One search: its text, how many records to return, a label for the trace, and, for a
    registry that files records by type (FAIRsharing), the type to search."""

    text: str
    limit: int = 10
    label: str = ""
    record_type: str | None = None

    def describe(self) -> str:
        rt = f" [{self.record_type}]" if self.record_type else ""
        return f"{self.label or 'query'}: {self.text!r}{rt}"


@dataclass(frozen=True)
class Hit[R = Any]:
    """A record a search found, with its lexical score (BM25, or a rank position for a registry
    that gives no score). The record's type defaults to `Any`, for a caller that does not say."""

    record: R
    lexical_score: float


@dataclass(frozen=True)
class SnapshotRef:
    """Which copy of a registry answered. It is the evidence's `snapshot_ref`, by which the
    harness's source check finds its own copy (docs/specs/grounding.md)."""

    label: str
    stale: bool = False
    fetched_at: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_string(self) -> str:
        return self.label + (" (stale)" if self.stale else "")

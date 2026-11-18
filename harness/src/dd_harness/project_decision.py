"""A person's decision on a version of a document, as they sent it (docs/specs/projects.md,
invariant 13). The record only: `dd_harness.projects.decisions` checks it, and
`dd_harness.storage` names it, so it lives below both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

type Verdict = Literal["approved", "rejected"]


@dataclass(frozen=True)
class Decision:
    """What a person sent: the version they saw, the digest of its text as shown, their verdict
    and reason, and, to approve an edit of it, the edited text. It never names who decided.
    `dd_harness.projects.decisions.check_decision` raises for one malformed in itself."""

    document_id: str
    version: int
    digest: str
    verdict: Verdict
    reason: str | None = None
    edited_text: str | None = None

    @property
    def stated_reason(self) -> str | None:
        return (self.reason or "").strip() or None

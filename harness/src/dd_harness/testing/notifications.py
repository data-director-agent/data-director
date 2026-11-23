"""A notifier that keeps what it was asked to send, for tests of who is told what
(`dd_harness.notifications`, docs/specs/stewardship.md, invariant 13)."""

from __future__ import annotations

from dataclasses import dataclass, field

from dd_harness.notifications import Notice


@dataclass
class RecordingNotifier:
    """Keeps each `(address, notice)` it is asked to send, in order, and sends nothing."""

    sent: list[tuple[str, Notice]] = field(default_factory=list)

    def send(self, address: str, notice: Notice) -> None:
        self.sent.append((address, notice))

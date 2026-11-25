"""The deployment's security events as an operator reads them (docs/guide/operations/admin.md,
"Security"): sign-ins and refusals, grants and enrolments, steward actions, case exports.

Each service writes one JSON line per event to the `dd.security` logger, which lands in its unit's
journal (`dd_sdk.security_log`, docs/specs/security.md). This reads the journal of the
deployment's units for a window and keeps the lines that are such records, by the same
`dd_harness.casefile` reader a downloaded case uses. A line is data, not a promise: any process
that logs to a unit can write one, so only the fields a record is defined to carry are kept, each
cut to a length, and a value is never read as markup or as a link target.

Nothing here writes, and no record carries a secret (the log's own rule): the page shows what a
service chose to record, which is reason codes and identifiers, never a message or a note.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from dd_admin.settings import AdminSettings
from dd_admin.system import System
from dd_harness.casefile.journal import journal_command, journal_lines
from dd_sdk.security_log import CONTEXT_KEYS

# The windows the page offers, in days, and the most entries it keeps from one.
WINDOWS = (1, 7)
MAX_ENTRIES = 1000
FIELD_LENGTH = 200
# A security record is written with these separators, so this finds its lines in the journal.
MARKER = '"outcome":"'
FIXED = ("time", "event", "outcome", "service", "principal", "reason")


@dataclass(frozen=True)
class Entry:
    at: str
    event: str
    outcome: str
    service: str
    principal: str
    reason: str
    context: tuple[tuple[str, str], ...] = ()


@dataclass
class Events:
    """`error` is set when the journal could not be read at all."""

    configured: bool = False
    error: str | None = None
    days: int = WINDOWS[0]
    entries: list[Entry] = field(default_factory=list)
    truncated: bool = False
    searched: bool = True

    @property
    def names(self) -> list[str]:
        return sorted({e.event for e in self.entries})

    @property
    def services(self) -> list[str]:
        return sorted({e.service for e in self.entries})

    @property
    def failures(self) -> int:
        return sum(1 for e in self.entries if e.outcome == "failure")


def _text(value: object) -> str:
    """A field as short text: a list is joined, anything else is its string, all cut."""
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    return "" if value is None else str(value)[:FIELD_LENGTH]


def entry(line: dict[str, Any]) -> Entry | None:
    """The security record in a journal `line`, or None for one that is not a record."""
    record = line.get("record")
    if not isinstance(record, dict) or record.get("outcome") not in {"success", "failure"}:
        return None
    if not isinstance(record.get("event"), str) or not isinstance(record.get("service"), str):
        return None
    return Entry(
        at=_text(record.get("time") or line.get("at")),
        event=_text(record["event"]),
        outcome=str(record["outcome"]),
        service=_text(record["service"]),
        principal=_text(record.get("principal")),
        reason=_text(record.get("reason")),
        context=tuple(
            (key, _text(record[key])) for key in sorted(CONTEXT_KEYS) if record.get(key) is not None
        ),
    )


def parse(text: str) -> list[Entry]:
    """The records in `journalctl --output json` output, newest first."""
    found = [e for line in journal_lines(text, [MARKER]) if (e := entry(line)) is not None]
    return sorted(found, key=lambda e: e.at, reverse=True)


def read(
    settings: AdminSettings, system: System, days: int = WINDOWS[0], now: datetime | None = None
) -> Events:
    """The security events of the last `days` days. The journal is searched for the records, and
    read whole if this machine's `journalctl` cannot search."""
    found = Events(days=days)
    if not settings.systemd:
        return found
    found.configured = True
    until = now or datetime.now(UTC)
    command = journal_command(until - timedelta(days=days), until)
    done = system.run(*command, "--grep", MARKER)
    if done.status != 0:
        found.searched = False
        done = system.run(*command)
    if done.status != 0:
        found.error = (done.err or done.out or f"journalctl exited {done.status}").strip()
        return found
    entries = parse(done.out)
    found.truncated = len(entries) > MAX_ENTRIES
    found.entries = entries[:MAX_ENTRIES]
    return found


def select(found: Events, event: str = "", outcome: str = "", service: str = "") -> list[Entry]:
    """The entries that match each filter given."""
    return [
        e
        for e in found.entries
        if (not event or e.event == event)
        and (not outcome or e.outcome == outcome)
        and (not service or e.service == service)
    ]

"""Who uses the deployment, and how: every run and project in the stores, across every person
(docs/guide/operations/admin.md, "What it shows of people").

The admin service reads both stores whole and keeps what it found for a minute (`dd_admin.cache`),
which is enough for an alpha's stores. A store too large for that is a database, whose listings
could page from its index instead (docs/guide/operations/admin.md, "Limits of the alpha").
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from dd_harness.storage import ProjectStorage, RunStorage

DAYS_CHARTED = 30


def _when(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        found = datetime.fromisoformat(value)
    except ValueError:
        return None
    return found if found.tzinfo else found.replace(tzinfo=UTC)


@dataclass
class Person:
    """Someone a run acted for or who created a project."""

    principal_id: str
    name: str
    assurance: str | None = None
    runs: int = 0
    conversations: set[str] = field(default_factory=set)
    projects: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    def saw(self, when: datetime | None) -> None:
        if when is None:
            return
        if self.first_seen is None or when < self.first_seen:
            self.first_seen = when
        if self.last_seen is None or when > self.last_seen:
            self.last_seen = when


@dataclass
class Usage:
    """What the stores hold, counted."""

    made_at: datetime
    runs: list[dict[str, Any]] = field(default_factory=list)  # newest first
    projects: list[dict[str, Any]] = field(default_factory=list)  # newest first
    people: list[Person] = field(default_factory=list)  # most recently seen first
    by_status: Counter[str] = field(default_factory=Counter)
    by_agent: dict[str, Counter[str]] = field(default_factory=dict)
    per_day: list[tuple[str, int]] = field(default_factory=list)  # oldest first
    input_tokens: int = 0
    output_tokens: int = 0
    errors: list[str] = field(default_factory=list)

    def runs_since(self, days: int) -> int:
        since = self.made_at - timedelta(days=days)
        return sum(1 for run in self.runs if run["at"] is not None and run["at"] >= since)

    def projects_since(self, days: int) -> int:
        since = self.made_at - timedelta(days=days)
        return sum(1 for p in self.projects if p["at"] is not None and p["at"] >= since)

    def active_people(self, days: int) -> int:
        since = self.made_at - timedelta(days=days)
        return sum(1 for p in self.people if p.last_seen is not None and p.last_seen >= since)

    def tokens_since(self, days: int) -> tuple[int, int]:
        """Model tokens in and out on runs that finished in the last `days`."""
        since = self.made_at - timedelta(days=days)
        recent = [r for r in self.runs if r["at"] is not None and r["at"] >= since]
        return sum(r["input_tokens"] for r in recent), sum(r["output_tokens"] for r in recent)

    def person(self, principal_id: str) -> Person | None:
        return next((p for p in self.people if p.principal_id == principal_id), None)


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def model_calls(telemetry: dict[str, Any]) -> list[tuple[str, int, int]]:
    """The run's tokens by model, as (model_id, in, out): one entry per call the agent reported
    (docs/specs/disclosure.md), or the run's totals under its one model if it reported none."""
    calls = [
        (
            str(c.get("model_id") or "unknown"),
            _int(c.get("input_tokens")),
            _int(c.get("output_tokens")),
        )
        for c in telemetry.get("model_calls") or []
        if isinstance(c, dict)
    ]
    if any(i or o for _, i, o in calls):
        return calls
    totals = (_int(telemetry.get("input_tokens")), _int(telemetry.get("output_tokens")))
    if not any(totals):
        return []
    return [(str(telemetry.get("model_id") or "unknown"), *totals)]


def run_row(envelope: dict[str, Any]) -> dict[str, Any]:
    """What the run list shows of one run."""
    acting_for = envelope.get("acting_for") or {}
    outcome = envelope.get("outcome") or {}
    telemetry = envelope.get("telemetry") or {}
    return {
        "invocation_id": envelope.get("invocation_id"),
        "agent_id": envelope.get("agent_id"),
        "agent_version": envelope.get("agent_version"),
        "status": outcome.get("status"),
        "reason_code": outcome.get("reason_code"),
        "at": _when(envelope.get("completed_at")),
        "principal_id": acting_for.get("principal_id"),
        "principal_name": acting_for.get("name"),
        "project_id": envelope.get("project_id"),
        "conversation_id": envelope.get("conversation_id"),
        "delegated": bool(envelope.get("parent_invocation_id")),
        "input_tokens": _int(telemetry.get("input_tokens")),
        "output_tokens": _int(telemetry.get("output_tokens")),
        "calls": model_calls(telemetry),
    }


def count(
    runs: RunStorage | None, projects: ProjectStorage | None, now: datetime | None = None
) -> Usage:
    """Read both stores and count what they hold. A store that cannot be read is named in
    `errors` and counted as empty, so the rest of the page still shows."""
    now = now or datetime.now(UTC)
    usage = Usage(made_at=now)
    people: dict[str, Person] = {}

    def person(acted_for: dict[str, Any]) -> Person | None:
        principal_id = acted_for.get("principal_id")
        if not principal_id:
            return None
        found = people.get(principal_id)
        if found is None:
            found = people[principal_id] = Person(
                principal_id=principal_id,
                name=str(acted_for.get("name") or principal_id),
                assurance=acted_for.get("assurance"),
            )
        return found

    if runs is not None:
        try:
            envelopes = list(runs.iter_envelopes())
        except Exception as exc:  # noqa: BLE001 - any backend failure is shown, not raised
            usage.errors.append(f"the run store cannot be read: {exc}")
            envelopes = []
        for envelope in envelopes:
            row = run_row(envelope)
            usage.runs.append(row)
            usage.by_status[row["status"] or "unknown"] += 1
            usage.by_agent.setdefault(row["agent_id"] or "unknown", Counter())[
                row["status"] or "unknown"
            ] += 1
            usage.input_tokens += int(row["input_tokens"])
            usage.output_tokens += int(row["output_tokens"])
            who = person(envelope.get("acting_for") or {})
            if who is not None:
                who.saw(row["at"])
                if not row["delegated"]:
                    who.runs += 1
                if row["conversation_id"]:
                    who.conversations.add(row["conversation_id"])
        usage.runs.reverse()

    if projects is not None:
        try:
            summaries = projects.projects()
        except Exception as exc:  # noqa: BLE001 - any backend failure is shown, not raised
            usage.errors.append(f"the project store cannot be read: {exc}")
            summaries = []
        for summary in summaries:
            created_by = summary.get("created_by") or {}
            at = _when(summary.get("created_at"))
            usage.projects.append({**summary, "at": at})
            who = person(created_by)
            if who is not None:
                who.projects += 1
                who.saw(at)
        usage.projects.reverse()

    days = [(now - timedelta(days=n)).date() for n in range(DAYS_CHARTED - 1, -1, -1)]
    per_day = Counter(run["at"].date() for run in usage.runs if run["at"] is not None)
    usage.per_day = [(day.isoformat(), per_day.get(day, 0)) for day in days]
    usage.people = sorted(
        people.values(),
        key=lambda p: p.last_seen or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return usage

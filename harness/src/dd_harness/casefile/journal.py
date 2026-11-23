"""The service journal lines that belong to a case (docs/specs/casefile.md, Journal): those of the
deployment's units, in the case's time span, that name one of its runs, conversations, project or
traces. The journal is read through a `Journal`, so a test, or the admin service with its own way
of running commands, needs no journal of its own.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

JOURNAL = "journal.jsonl"
# Every unit of a deployment is named `data-director…` (deploy/systemd/).
UNITS = "data-director*"
# Lines a little before the first record and after the last belong to the case too: a request is
# logged before its run starts, and a failure after its run is stored.
PADDING = timedelta(minutes=5)
TIMEOUT_S = 60.0

# `journalctl --output json` for a time span: the text it prints.
Journal = Callable[[datetime, datetime], str]


def journal_command(since: datetime, until: datetime) -> list[str]:
    """The `journalctl` command that prints the deployment's units' lines from `since` to
    `until`, one JSON object a line."""
    return [
        "journalctl",
        "--output",
        "json",
        "--no-pager",
        "--unit",
        UNITS,
        "--since",
        f"@{int(since.timestamp())}",
        "--until",
        f"@{int(until.timestamp()) + 1}",
    ]


def read_journal(since: datetime, until: datetime) -> str:
    """The journal of this machine, as `journalctl` prints it. `OSError`, with what `journalctl`
    said, if it cannot be read: an operator who asks for the journal is told, not handed a case
    without it."""
    try:
        done = subprocess.run(
            journal_command(since, until),
            capture_output=True,
            text=True,
            check=True,
            timeout=TIMEOUT_S,
        )
    except subprocess.CalledProcessError as exc:
        said = (exc.stderr or exc.stdout or "").strip() or f"exited {exc.returncode}"
        raise OSError(f"journalctl: {said}") from exc
    except subprocess.TimeoutExpired as exc:
        raise OSError(f"journalctl: no answer within {TIMEOUT_S:.0f} s") from exc
    return done.stdout


def span(times: Iterable[str]) -> tuple[datetime, datetime] | None:
    """The padded span of ISO 8601 `times`, or None if there are none."""
    moments = [_moment(t) for t in times]
    if not moments:
        return None
    return min(moments) - PADDING, max(moments) + PADDING


def _moment(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _message(entry: Mapping[str, Any]) -> str:
    """A journal entry's message; journald gives one that is not UTF-8 as a list of bytes."""
    message = entry.get("MESSAGE")
    if isinstance(message, list):
        return bytes(b for b in message if isinstance(b, int)).decode("utf-8", "replace")
    return str(message or "")


def _record(message: str) -> dict[str, Any] | None:
    """The JSON object a structured line (the security log) carries, if it is one."""
    if not message.startswith("{"):
        return None
    try:
        value = json.loads(message)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def journal_lines(text: str, identifiers: Iterable[str]) -> Iterator[dict[str, Any]]:
    """Each line of `journalctl --output json` output that names one of `identifiers`, as `at`,
    `unit`, `priority` and either `record`, for a line that is a JSON object, or `message`."""
    names = [i for i in set(identifiers) if i]
    for raw in text.splitlines():
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        message = _message(entry)
        if not isinstance(entry, dict) or not any(name in message for name in names):
            continue
        micros = int(entry.get("__REALTIME_TIMESTAMP") or 0)
        at = datetime.fromtimestamp(micros / 1_000_000, UTC)
        line: dict[str, Any] = {
            "at": at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "unit": entry.get("_SYSTEMD_UNIT") or entry.get("SYSLOG_IDENTIFIER"),
            "priority": entry.get("PRIORITY"),
        }
        record = _record(message)
        if record is not None:
            line["record"] = record
        else:
            line["message"] = message
        yield line

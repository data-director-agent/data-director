"""The security event log: one JSON record per event on the `dd.security` logger.

Security events record who signed in and in which deployment roles, who was refused, which
profile a service loaded, what a data steward read or did in another person's project, which model
grants were minted and which accounts were enrolled with the model broker (docs/specs/security.md,
Security events). They are kept apart from run provenance, which records what an agent did
(invariant 5).

A record carries only the fields `emit` builds: a time, the event, its outcome, a principal, a
reason code, the service and a few named identifiers. A caller cannot add another field, so a
token, key or session id has no field to travel in (invariant 2).

Each service calls `configure()` once at start-up, which writes the records to standard error as
one JSON line each; under systemd the journal keeps them.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from enum import StrEnum
from typing import IO, Any, Literal

LOGGER = "dd.security"

log = logging.getLogger(LOGGER)


class SecurityEvent(StrEnum):
    SIGN_IN_SUCCEEDED = "sign-in.succeeded"
    SIGN_IN_FAILED = "sign-in.failed"
    SIGN_OUT = "sign-out"
    SESSION_ENDED = "session.ended"
    ACCESS_LOADED = "access.loaded"
    CALLER_REFUSED = "caller.refused"
    PROFILE_LOADED = "profile.loaded"
    STEWARD_VIEWED = "steward.viewed"
    STEWARD_ACTED = "steward.acted"
    GRANT_MINTED = "grant.minted"
    BROKER_BYPASS_REFUSED = "agent.broker-bypass-refused"
    BROKER_ENROLLED = "broker.enrolled"
    BROKER_ENROLMENT_REFUSED = "broker.enrolment-refused"
    BROKER_ACCOUNT_REMOVED = "broker.account-removed"
    BROKER_CALL_REFUSED = "broker.call-refused"
    SPAN_SECRET_DROPPED = "agent.span-secret-dropped"
    CASE_EXPORTED = "case.exported"


type Outcome = Literal["success", "failure"]

# The identifiers a record may carry beside its fixed fields. None of them is a secret.
CONTEXT_KEYS = frozenset(
    {
        "agent_id",
        "invocation_id",
        "conversation_id",
        "profile_id",
        "profile_version",
        "project_id",
        "action",
        "roles",
        "provider",
        "models",
        "account",
        "transport",
    }
)

# The attribute of a `LogRecord` that holds the event's fields.
_FIELDS = "dd_security"


def emit(
    event: SecurityEvent,
    *,
    outcome: Outcome,
    service: str,
    principal: str | None = None,
    reason: str | None = None,
    **context: str | int | list[str],
) -> None:
    """Record one security event. `principal` is the person's identifier where the service knows
    it, or their pseudonym in the broker, which knows nothing else; `reason` is a reason code,
    never a message. Raises `ValueError` for a context key outside `CONTEXT_KEYS`."""
    unknown = context.keys() - CONTEXT_KEYS
    if unknown:
        raise ValueError(f"a security event carries no field {sorted(unknown)!r}")
    # Plain `str`, not a `StrEnum` member: a record's fields must survive any serialiser that
    # checks exact types (pytest-xdist's execnet, for one), not only `json`.
    if isinstance(principal, str):
        principal = str(principal)
    if isinstance(reason, str):
        reason = str(reason)
    context = {
        key: [str(v) for v in value]
        if isinstance(value, list)
        else str(value)
        if isinstance(value, str)
        else value
        for key, value in context.items()
    }
    fields: dict[str, Any] = {
        "time": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "event": event.value,
        "outcome": outcome,
        "service": service,
        "principal": principal,
        "reason": reason,
        **context,
    }
    level = logging.INFO if outcome == "success" else logging.WARNING
    log.log(level, event.value, extra={_FIELDS: fields})


def fields(record: logging.LogRecord) -> dict[str, Any]:
    """The fields of a record `emit` made: what `JsonFormatter` writes, and what tests read."""
    found = getattr(record, _FIELDS, None)
    if not isinstance(found, dict):
        raise ValueError("not a security event record")
    return found


class JsonFormatter(logging.Formatter):
    """Writes a security event as one line of JSON, and nothing else."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(fields(record), ensure_ascii=False, separators=(",", ":"))


def configure(stream: IO[str] | None = None) -> None:
    """Send security events to `stream` (standard error by default) as JSON lines, and not to
    the root logger's handlers, so they are never mixed with free-text lines. Idempotent."""
    for handler in list(log.handlers):
        if getattr(handler, "dd_security", False):
            log.removeHandler(handler)
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.dd_security = True  # type: ignore[attr-defined]
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False

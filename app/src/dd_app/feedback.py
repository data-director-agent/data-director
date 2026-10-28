"""Problem reports and feature requests, filed as GitHub issues (`POST /api/feedback`).

The server holds one fine-grained token (Issues: write, this repository only) and files the
issue for the reporter, who needs no GitHub account. The issue is public, so the page says so and
shows what will be sent. The server adds the build's version and commit itself, and for a run or
conversation the reporter chose to include, only its identifiers, agents, versions and outcome:
never a payload, an input or evidence. Without a token the feature is off (ADR-0030).
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from dd_sdk.credentials import ConfigError

TOKEN_VARIABLE = "DD_FEEDBACK_GITHUB_TOKEN"
REPO_VARIABLE = "DD_FEEDBACK_REPO"
DEFAULT_REPO = "data-director-agent/data-director"
GITHUB_API = "https://api.github.com"
GITHUB_TIMEOUT_SECONDS = 15.0

TITLE_LIMIT = 120
DESCRIPTION_LIMIT = 5000
CONTEXT_FIELD_LIMIT = 200
# TODO(#188): settle the numbers with the first real use.
RATE_LIMIT = 5
RATE_WINDOW_SECONDS = 600

# The issue type (GitHub's organisation issue types) for each kind of report.
KINDS = {"bug": "Bug", "feature": "Feature", "other": "Task"}
LABELS = ["area: app"]


class FeedbackRefusedError(ValueError):
    """The report is not acceptable as sent. The message says why, for the reporter."""


class FeedbackFailedError(RuntimeError):
    """GitHub did not accept the issue."""


class RateLimitedError(RuntimeError):
    """Too many reports from this reporter lately."""


@dataclass(frozen=True)
class Report:
    kind: str
    title: str
    description: str
    page: str | None = None
    run: str | None = None
    conversation: str | None = None
    include_context: bool = False


def parse(body: object) -> Report:
    """A `Report` from a request body, or `FeedbackRefusedError`."""
    if not isinstance(body, dict):
        raise FeedbackRefusedError("The body must be an object.")
    if extra := sorted(set(body) - set(Report.__dataclass_fields__)):
        raise FeedbackRefusedError(f"A report takes no {extra}.")
    kind = body.get("kind")
    if kind not in KINDS:
        raise FeedbackRefusedError(f"`kind` must be one of {sorted(KINDS)}.")
    title, description = body.get("title"), body.get("description")
    if not isinstance(title, str) or not title.strip():
        raise FeedbackRefusedError("Give the report a title.")
    if not isinstance(description, str) or not description.strip():
        raise FeedbackRefusedError("Describe the problem or the request.")
    if len(title.strip()) > TITLE_LIMIT:
        raise FeedbackRefusedError(f"The title is longer than {TITLE_LIMIT} characters.")
    if len(description.strip()) > DESCRIPTION_LIMIT:
        raise FeedbackRefusedError(
            f"The description is longer than {DESCRIPTION_LIMIT} characters."
        )
    include = body.get("include_context", False)
    if not isinstance(include, bool):
        raise FeedbackRefusedError("`include_context` must be true or false.")
    optional: dict[str, str | None] = {}
    for name in ("page", "run", "conversation"):
        value = body.get(name)
        if value is not None and (not isinstance(value, str) or len(value) > CONTEXT_FIELD_LIMIT):
            raise FeedbackRefusedError(f"`{name}` must be a short string.")
        optional[name] = value or None
    return Report(
        kind=kind,
        title=" ".join(title.split()),
        description=description.strip(),
        include_context=include,
        **optional,
    )


@dataclass
class RateLimiter:
    """At most `limit` reports in `window` seconds, counted for the whole process."""

    limit: int = RATE_LIMIT
    window: float = RATE_WINDOW_SECONDS
    clock: Any = time.monotonic
    _times: deque[float] = field(default_factory=deque)

    def check(self) -> None:
        now = self.clock()
        while self._times and now - self._times[0] >= self.window:
            self._times.popleft()
        if len(self._times) >= self.limit:
            raise RateLimitedError("Too many reports lately; try again in a few minutes.")
        self._times.append(now)


def token_from_env(env: Mapping[str, str]) -> str | None:
    """The GitHub token, from `DD_FEEDBACK_GITHUB_TOKEN` or the file `..._FILE` (resolved as
    `dd_sdk.credentials.api_key` does), or None if neither is set: the feature is then off."""
    value, file = (env.get(TOKEN_VARIABLE) or "").strip(), env.get(f"{TOKEN_VARIABLE}_FILE")
    if value and file:
        raise ConfigError(f"set {TOKEN_VARIABLE} or {TOKEN_VARIABLE}_FILE, not both")
    if value or not file:
        return value or None
    path = Path(file)
    if not path.is_absolute():
        directory = env.get("CREDENTIALS_DIRECTORY")
        if not directory:
            raise ConfigError(
                f"{TOKEN_VARIABLE}_FILE={file} is relative and CREDENTIALS_DIRECTORY is not set"
            )
        path = Path(directory) / path
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ConfigError(f"{TOKEN_VARIABLE}_FILE: cannot read {path}: {exc.strerror}") from exc
    if not token:
        raise ConfigError(f"{TOKEN_VARIABLE}_FILE: {path} is empty")
    return token


def run_context(stored: Mapping[str, Any]) -> list[str]:
    """The lines about a stored run that a report may carry: identifiers and outcome only."""
    envelope = stored.get("envelope") or {}
    outcome = envelope.get("outcome") or {}
    return [
        f"- Run `{envelope.get('invocation_id')}`: agent `{envelope.get('agent_id')}` "
        f"{envelope.get('agent_version')}, outcome `{outcome.get('status')}`"
        + (f" (`{outcome['reason_code']}`)" if outcome.get("reason_code") else ""),
    ]


def conversation_context(found: Mapping[str, Any]) -> list[str]:
    turns = found.get("turns") or []
    lines = [f"- Conversation `{found.get('conversation_id')}`: {len(turns)} turn(s)"]
    for turn in turns:
        lines.append(
            f"  - run `{turn.get('invocation_id')}`: agent `{turn.get('agent_id')}` "
            f"{turn.get('agent_version')}, `{turn.get('status')}`"
        )
    return lines


def issue_body(report: Report, build: Mapping[str, str | None], context: list[str]) -> str:
    commit = build.get("commit")
    lines = [
        report.description,
        "",
        "---",
        "Reported from the app.",
        "",
        f"- Kind: {report.kind}",
        f"- App version: `{build.get('app_version') or 'unknown'}`",
        f"- Harness version: `{build.get('harness_version') or 'unknown'}`",
        f"- Commit: `{commit or 'unknown'}`",
    ]
    if report.page:
        lines.append(f"- Page: `{report.page}`")
    lines += context
    return "\n".join(lines)


async def create_issue(
    report: Report,
    body: str,
    *,
    repo: str,
    token: str,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    """File the issue; its `html_url` and `number`. GitHub's refusal is a `FeedbackFailedError`.

    The issue type is set where the organisation has types; where GitHub does not accept one for
    this repository the issue is filed without it.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload: dict[str, Any] = {
        "title": report.title,
        "body": body,
        "labels": LABELS,
        "type": KINDS[report.kind],
    }
    url = f"{GITHUB_API}/repos/{repo}/issues"
    try:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 422 and "type" in payload:
            del payload["type"]
            response = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise FeedbackFailedError(f"GitHub could not be reached ({type(exc).__name__}).") from exc
    if response.status_code != 201:
        raise FeedbackFailedError(f"GitHub answered {response.status_code}.")
    created = response.json()
    return {"url": created["html_url"], "number": created["number"]}

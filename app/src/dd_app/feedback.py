"""Problem reports and feature requests, filed as GitHub issues (`POST /api/feedback`).

The server holds a credential for GitHub (a GitHub App's key, or a fine-grained token; either
with Issues: write on this repository only, `github_auth.py`) and files the issue for the
reporter, who needs no GitHub account. The issue is public, so the page says so and
shows what will be sent. The server adds the build's version and commit itself, and for a run or
conversation the reporter chose to include, only its identifiers, agents, versions and outcome:
never a payload, an input or evidence. Without a credential the feature is off (docs/specs/app.md).
"""

from __future__ import annotations

import platform
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from dd_app.github_auth import (
    GITHUB_API,
    TOKEN_VARIABLE,
    GitHubAuthError,
    TokenSource,
    headers,
    source_from_env,
    token_from_env,
)

__all__ = ["TOKEN_VARIABLE", "source_from_env", "token_from_env"]

REPO_VARIABLE = "DD_FEEDBACK_REPO"
DEFAULT_REPO = "data-director-agent/data-director"
GITHUB_TIMEOUT_SECONDS = 15.0

TITLE_LIMIT = 120
DESCRIPTION_LIMIT = 5000
CONTEXT_FIELD_LIMIT = 200
# What the browser says about itself, each value bounded and only these names accepted.
CLIENT_FIELDS = ("user_agent", "language", "viewport", "color_scheme")
CLIENT_FIELD_LIMIT = 300
# TODO(#188): settle the numbers with the first real use.
RATE_LIMIT = 5
RATE_WINDOW_SECONDS = 600

# The issue type (GitHub's organisation issue types) for each kind of report.
KINDS = {"bug": "Bug", "feature": "Feature", "other": "Task"}
LABELS = ["area: app"]
# A bug someone took the trouble to write up stands out on the project board (a label to filter
# and colour by) because it comes from a person using the app, not from the team.
USER_REPORT_LABEL = "user report"


def labels_for(kind: str) -> list[str]:
    """The labels for a report of this kind."""
    return [*LABELS, USER_REPORT_LABEL] if kind == "bug" else list(LABELS)


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
    client: Mapping[str, str] | None = None
    """What the reporter's browser said about itself (`CLIENT_FIELDS`), shown to them first."""


def parse_client(value: object) -> dict[str, str] | None:
    """The browser details in a request body, or `FeedbackRefusedError`."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - set(CLIENT_FIELDS):
        raise FeedbackRefusedError(f"`client` takes only {list(CLIENT_FIELDS)}.")
    found: dict[str, str] = {}
    for name, text in value.items():
        if not isinstance(text, str) or len(text) > CLIENT_FIELD_LIMIT:
            raise FeedbackRefusedError(f"`client.{name}` must be a short string.")
        if cleaned := " ".join(text.split()):
            found[name] = cleaned
    return found or None


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
        client=parse_client(body.get("client")),
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


def deployment_lines(deployment: Mapping[str, Any]) -> list[str]:
    """What the deployment runs, as `GET /api/about` names it: no addresses, no reasons."""
    profile = deployment.get("profile") or {}
    lines = [
        f"- Profile: `{profile.get('id')}` v{profile.get('version')} "
        f"(digest `{str(profile.get('digest') or 'unknown')[:12]}`)",
        f"- Orchestrator: `{profile.get('orchestrator') or 'none'}`",
    ]
    for label, key in (
        ("Unreachable agents", "unavailable"),
        ("Incompatible agents", "incompatible"),
    ):
        if names := deployment.get(key):
            lines.append(f"- {label}: " + ", ".join(f"`{name}`" for name in names))
    return lines


def client_lines(client: Mapping[str, str] | None) -> list[str]:
    labels = {
        "user_agent": "Browser",
        "language": "Language",
        "viewport": "Viewport",
        "color_scheme": "Colour scheme",
    }
    return [
        f"- {labels[name]}: `{client[name]}`" for name in CLIENT_FIELDS if client and name in client
    ]


def issue_body(
    report: Report,
    build: Mapping[str, str | None],
    context: list[str],
    deployment: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> str:
    """The issue's text: what was typed, then the build and, folded away, the setting it ran in.

    Everything after the description is read by the server or shown to the reporter before it is
    sent; none of it is a person's work (docs/specs/app.md).
    """
    commit = build.get("commit")
    filed = (now or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")
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
    environment = [
        f"- Filed: {filed}",
        f"- Server: Python {platform.python_version()} on {platform.system()}",
        *deployment_lines(deployment or {}),
        *client_lines(report.client),
    ]
    lines += ["", "<details><summary>Environment</summary>", "", *environment, "", "</details>"]
    return "\n".join(lines)


async def create_issue(
    report: Report,
    body: str,
    *,
    repo: str,
    source: TokenSource,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    """File the issue; its `html_url` and `number`. GitHub's refusal is a `FeedbackFailedError`.

    The issue type is set where the organisation has types; where GitHub does not accept one for
    this repository the issue is filed without it. If GitHub refuses the token and the source can
    make another (an App's installation token revoked or expired early), it is asked once more.
    """
    payload: dict[str, Any] = {
        "title": report.title,
        "body": body,
        "labels": labels_for(report.kind),
        "type": KINDS[report.kind],
    }
    url = f"{GITHUB_API}/repos/{repo}/issues"

    async def post() -> httpx.Response:
        return await client.post(url, json=payload, headers=headers(await source.token(client)))

    try:
        response = await post()
        if response.status_code == 401 and source.invalidate():
            response = await post()
        if response.status_code == 422 and "type" in payload:
            del payload["type"]
            response = await post()
    except GitHubAuthError as exc:
        raise FeedbackFailedError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise FeedbackFailedError(f"GitHub could not be reached ({type(exc).__name__}).") from exc
    if response.status_code != 201:
        raise FeedbackFailedError(f"GitHub answered {response.status_code}.")
    created = response.json()
    return {"url": created["html_url"], "number": created["number"]}

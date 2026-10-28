"""Problem reports: the build's identity, and `POST /api/feedback` against a stand-in GitHub."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient
from support import configure_env, dist_dir, new_governance

from dd_app import feedback
from dd_app.about import about, commit
from dd_app.app import build_app
from dd_app.governance import Governance
from dd_sdk.credentials import ConfigError


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return configure_env(monkeypatch, tmp_path)


@pytest.fixture
def governance(env: Path) -> Iterator[Governance]:
    yield from new_governance()


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    return dist_dir(tmp_path)


BUILD = {"app_version": "1.2.3", "harness_version": "0.4.5", "commit": "abc1234def"}
REPORT = {"kind": "bug", "title": "  The run  hangs ", "description": "It never ends."}


def client_for(
    governance: Governance,
    dist: Path,
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
    token: str | None = "t0ken",
) -> tuple[TestClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if handler:
            return handler(request)
        return httpx.Response(201, json={"html_url": "https://github.test/i/7", "number": 7})

    github = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    app = build_app(governance, dist, feedback_token=token, feedback_client=github, build=BUILD)
    return TestClient(app), seen


def test_commit_prefers_the_environment_then_the_release_file(tmp_path: Path) -> None:
    (tmp_path / "REVISION").write_text("fromfile\n", encoding="utf-8")
    assert commit({"DD_REVISION": "fromenv"}, tmp_path) == "fromenv"
    assert commit({}, tmp_path) == "fromfile"


def test_commit_is_none_where_nothing_tells_it(tmp_path: Path) -> None:
    assert commit({}, tmp_path) is None


def test_about_names_the_installed_versions(tmp_path: Path) -> None:
    found = about({"DD_REVISION": "x"}, tmp_path)
    assert found["commit"] == "x"
    assert found["app_version"] and found["harness_version"]


def test_about_says_whether_reports_are_on(governance: Governance, dist: Path) -> None:
    on, _ = client_for(governance, dist)
    off, _ = client_for(governance, dist, token=None)
    assert on.get("/api/about").json() == {**BUILD, "feedback_enabled": True}
    assert off.get("/api/about").json()["feedback_enabled"] is False


def test_a_report_files_an_issue_with_the_build(governance: Governance, dist: Path) -> None:
    client, seen = client_for(governance, dist)
    response = client.post("/api/feedback", json=REPORT)
    assert response.status_code == 201
    assert response.json() == {"url": "https://github.test/i/7", "number": 7}
    (request,) = seen
    assert request.url.path == "/repos/data-director-agent/data-director/issues"
    assert request.headers["authorization"] == "Bearer t0ken"
    sent = json.loads(request.content)
    assert sent["title"] == "The run hangs"
    assert sent["type"] == "Bug"
    assert sent["labels"] == ["area: app"]
    for line in ("`1.2.3`", "`0.4.5`", "`abc1234def`", "It never ends."):
        assert line in sent["body"]


def test_the_issue_type_is_dropped_where_github_refuses_it(
    governance: Governance, dist: Path
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "type" in json.loads(request.content):
            return httpx.Response(422, json={"message": "Validation Failed"})
        return httpx.Response(201, json={"html_url": "https://github.test/i/8", "number": 8})

    client, seen = client_for(governance, dist, handler)
    assert client.post("/api/feedback", json=REPORT).status_code == 201
    assert len(seen) == 2
    assert "Kind: bug" in json.loads(seen[1].content)["body"]


def test_no_token_means_no_reports(governance: Governance, dist: Path) -> None:
    client, seen = client_for(governance, dist, token=None)
    response = client.post("/api/feedback", json=REPORT)
    assert response.status_code == 503
    assert response.json()["type"].endswith("feedback-unavailable")
    assert not seen


@pytest.mark.parametrize(
    "body",
    [
        [],
        {**REPORT, "kind": "praise"},
        {**REPORT, "title": " "},
        {**REPORT, "description": ""},
        {**REPORT, "title": "x" * (feedback.TITLE_LIMIT + 1)},
        {**REPORT, "description": "x" * (feedback.DESCRIPTION_LIMIT + 1)},
        {**REPORT, "include_context": "yes"},
        {**REPORT, "labels": ["admin"]},
        {**REPORT, "run": 5},
    ],
)
def test_a_bad_report_is_refused_before_github(
    governance: Governance, dist: Path, body: Any
) -> None:
    client, seen = client_for(governance, dist)
    response = client.post("/api/feedback", json=body)
    assert response.status_code == 400
    assert not seen


def test_github_failing_is_a_502(governance: Governance, dist: Path) -> None:
    client, _ = client_for(governance, dist, lambda _: httpx.Response(500))
    response = client.post("/api/feedback", json=REPORT)
    assert response.status_code == 502
    assert "t0ken" not in response.text


def test_reports_are_rate_limited(governance: Governance, dist: Path) -> None:
    client, seen = client_for(governance, dist)
    statuses = [
        client.post("/api/feedback", json=REPORT).status_code
        for _ in range(feedback.RATE_LIMIT + 1)
    ]
    assert statuses == [201] * feedback.RATE_LIMIT + [429]
    assert len(seen) == feedback.RATE_LIMIT


def test_context_is_attached_only_with_consent_and_only_identifiers(
    governance: Governance, dist: Path
) -> None:
    started = governance.start_conversation()
    for consent in (False, True):
        client, seen = client_for(governance, dist)
        body = {**REPORT, "conversation": started, "include_context": consent}
        assert client.post("/api/feedback", json=body).status_code == 201
        text = json.loads(seen[0].content)["body"]
        assert (started in text) is consent


def test_the_token_comes_from_a_value_or_a_credential_file(tmp_path: Path) -> None:
    (tmp_path / "token").write_text("filed\n", encoding="utf-8")
    assert feedback.token_from_env({}) is None
    assert feedback.token_from_env({feedback.TOKEN_VARIABLE: " v "}) == "v"
    env = {
        f"{feedback.TOKEN_VARIABLE}_FILE": "token",
        "CREDENTIALS_DIRECTORY": str(tmp_path),
    }
    assert feedback.token_from_env(env) == "filed"
    with pytest.raises(ConfigError):
        feedback.token_from_env({**env, feedback.TOKEN_VARIABLE: "both"})
    with pytest.raises(ConfigError):
        feedback.token_from_env({f"{feedback.TOKEN_VARIABLE}_FILE": "token"})
    with pytest.raises(ConfigError):
        feedback.token_from_env({f"{feedback.TOKEN_VARIABLE}_FILE": str(tmp_path / "none")})

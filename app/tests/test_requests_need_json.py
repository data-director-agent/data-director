"""#728: the session cookie is `SameSite=Lax`, which a same-site, cross-origin form still rides,
so a request that changes state must declare JSON, which such a form cannot."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import configure_env, dist_dir, new_governance

from dd_app.app import build_app
from dd_app.governance import (
    Governance,
)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return configure_env(monkeypatch, tmp_path)


@pytest.fixture
def governance(env: Path) -> Iterator[Governance]:
    yield from new_governance()


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    return dist_dir(tmp_path)


def _state_changing_routes(app: Any) -> list[tuple[str, str]]:
    found = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/"):
            continue
        for method in sorted(getattr(route, "methods", None) or ()):
            if method in {"POST", "PUT", "PATCH", "DELETE"}:
                found.append((method, re.sub(r"\{[^}]+\}", "x", path)))
    return found


def test_every_state_changing_api_route_refuses_a_body_that_is_not_json(
    governance: Governance, dist: Path
):
    app = build_app(governance, dist)
    routes = _state_changing_routes(app)
    assert ("POST", "/api/runs") in routes and ("PUT", "/api/projects/x/title") in routes
    client = TestClient(app)
    for method, path in routes:
        for headers in (
            {"content-type": "text/plain"},
            {"content-type": "application/x-www-form-urlencoded"},
            {"content-type": "multipart/form-data; boundary=b"},
            {},
        ):
            response = client.request(method, path, content=b'{"a": 1}', headers=headers)
            assert response.status_code == 415, (method, path, headers)
            assert response.headers["content-type"].startswith("application/problem+json")
        bodyless = client.request(method, path, headers={"content-type": "text/plain"})
        assert bodyless.status_code == 415, (method, path)


def test_a_json_request_with_a_charset_is_not_refused_for_its_type(
    governance: Governance, dist: Path
):
    client = TestClient(build_app(governance, dist))
    response = client.post(
        "/api/runs", content=b"[]", headers={"content-type": "Application/JSON; charset=utf-8"}
    )
    assert response.status_code == 400

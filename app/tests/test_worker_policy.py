"""The browser scanner's assets get the headers they need (`dd_app.worker_policy`).

The worker is sent its own Content Security Policy, and the bundle is revalidated on every use.

An alpha substantiates no requirement, so these tests carry no requirement marker.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from support import configure_env, dist_dir, new_governance

from dd_app.app import build_app
from dd_app.worker_policy import BUNDLE_CACHING, WORKER_POLICY

WORKER = "assets/inventory-scanner-AbC123.js"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    configure_env(monkeypatch, tmp_path)
    dist = dist_dir(tmp_path)
    (dist / "assets").mkdir()
    (dist / WORKER).write_text("self.onmessage = () => {};", encoding="utf-8")
    (dist / "assets/index-AbC123.js").write_text("export {};", encoding="utf-8")
    bundle = dist / "inventory-bundle"
    bundle.mkdir()
    (bundle / "pyodide.asm.wasm").write_bytes(b"\0asm\1\0\0\0")
    for governance in new_governance():
        yield TestClient(build_app(governance, dist))


def test_the_worker_script_carries_the_worker_policy(client: TestClient) -> None:
    response = client.get(f"/{WORKER}")
    assert response.status_code == 200
    assert response.headers.get_list("content-security-policy") == [WORKER_POLICY]


@pytest.mark.parametrize(
    "path",
    ["/", "/assets/index-AbC123.js", "/inventory-bundle/pyodide.asm.wasm", "/api/about"],
)
def test_no_other_response_gets_the_worker_policy(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers


def test_the_bundle_is_served_with_types_a_browser_accepts(client: TestClient) -> None:
    response = client.get("/inventory-bundle/pyodide.asm.wasm")
    assert response.headers["content-type"] == "application/wasm"


def test_the_bundle_is_revalidated_on_every_use(client: TestClient) -> None:
    response = client.get("/inventory-bundle/pyodide.asm.wasm")
    assert response.headers.get_list("cache-control") == [BUNDLE_CACHING]
    assert "etag" in response.headers
    again = client.get(
        "/inventory-bundle/pyodide.asm.wasm",
        headers={"if-none-match": response.headers["etag"]},
    )
    assert again.status_code == 304
    assert again.headers.get_list("cache-control") == [BUNDLE_CACHING]


@pytest.mark.parametrize("path", ["/", f"/{WORKER}", "/assets/index-AbC123.js", "/api/about"])
def test_nothing_outside_the_bundle_gets_its_caching(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.headers.get("cache-control") != BUNDLE_CACHING

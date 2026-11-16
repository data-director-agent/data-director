"""What the app's tests share: environment, governance and app builders, and route helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from starlette.testclient import TestClient

from dd_agent_advisor_standards import factory as standards
from dd_agent_example_hello.agent import build as build_hello
from dd_agent_orchestrator_stub.agent import build as build_director
from dd_app.app import build_app
from dd_app.config import DEFAULT_PROFILE, settings_from_env
from dd_app.governance import (
    Governance,
)
from dd_harness.conductor import Conductor
from dd_harness.identity import OperatorAssertion
from dd_harness.policy import load_profile
from dd_harness.projects import ProjectStore
from dd_harness.registry import Registry
from dd_harness.store import RunStore
from dd_harness.testing import (
    TEST_PRINCIPAL,
    asgi_client_factory,
    in_process,
)

PATH_VARIABLES = ("DD_PROFILE", "DD_AGENTS_CONFIG", "DD_SOURCES_CONFIG", "DD_REPOSITORIES_DIR")
APP_URL = "http://app.test"
# The shell's component and browser tests are drawn from these, so each must be what the server
# says. Outside CI a test rewrites a fixture that has fallen behind, so running the tests locally
# keeps them current: commit what changed. In CI (`CI` set) a stale fixture fails instead, unless
# DD_WRITE_FIXTURES=1.
FIXTURES = Path(__file__).resolve().parents[1] / "web/fixtures"
# A re3data export pinned for a test: two repositories and the standards each declares.
ORDA = "r3d100012124"
ZENODO = "r3d100010468"
EXPORT = "re3data:export:2026-11"
# The fields a choice reads, as the export's registry.jsonl holds them.
RECORDS = (
    {
        "re3data_id": ORDA,
        "name": "ORDA - The University of Sheffield Research Data Catalogue and Repository",
        "metadata_standards": ["Dublin Core"],
        "url": "https://orda.shef.ac.uk/",
    },
    {
        "re3data_id": ZENODO,
        "name": "Zenodo",
        "metadata_standards": ["DataCite Metadata Schema"],
        "url": "https://zenodo.org/",
    },
)


# The app refuses a request that changes state unless it declares JSON, body or not (#728).
JSON_HEADERS = {"content-type": "application/json"}


def pin_export(root: Path) -> Path:
    """A `sources.yaml` pinning a re3data export of `RECORDS`, as `dd-re3data fetch` builds."""
    root.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r, sort_keys=True) + "\n" for r in RECORDS).encode()
    (root / "registry.jsonl").write_bytes(data)
    entry = {
        "snapshot_refs": [EXPORT],
        "path": "registry.jsonl",
        "id_field": "re3data_id",
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    config = root / "sources.yaml"
    config.write_text(yaml.safe_dump({"sources": [entry]}), "utf-8")
    return config


def _rewrite_fixtures() -> bool:
    if "DD_WRITE_FIXTURES" in os.environ:
        return os.environ["DD_WRITE_FIXTURES"] == "1"
    return not os.environ.get("CI")


def _changed_keys(old: Any, new: Any, where: str = "") -> list[str]:
    """Where `old` and `new` differ, as JSON paths, for the failure message."""
    if isinstance(old, dict) and isinstance(new, dict):
        return [
            change
            for key in sorted(old.keys() | new.keys())
            for change in _changed_keys(old.get(key), new.get(key), f"{where}.{key}")
        ]
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        return [
            change
            for i, (a, b) in enumerate(zip(old, new, strict=True))
            for change in _changed_keys(a, b, f"{where}[{i}]")
        ]
    return [] if old == new else [where or "."]


def check_fixture(name: str, body: Any) -> None:
    """`body` is what the fixture `name` holds; compared as JSON, so layout does not matter."""
    path = FIXTURES / name
    text = json.dumps(body, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    fresh = json.loads(text)
    held = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if held == fresh:
        return
    if _rewrite_fixtures():
        path.write_text(text, encoding="utf-8")
        return
    changed = ", ".join(_changed_keys(held, fresh)[:10])
    raise AssertionError(
        f"{path.name} is stale (changed: {changed}). Run `uv run pytest app/tests` locally, "
        "which rewrites it, and commit the result."
    )


# AG-UI streams the shell replays (docs/specs/transport.md), one event per line, kept like the
# fixtures above. `scripts/record_ui_cassettes.py` rewrites them all.
CASSETTES = Path(__file__).resolve().parents[1] / "web/cassettes"


def check_cassette(name: str, events: list[dict[str, Any]]) -> None:
    """`events` is what the cassette `name` holds, one JSON object a line, compared as JSON."""
    path = CASSETTES / name
    text = "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in events)
    held = (
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        if path.exists()
        else None
    )
    if held == events:
        return
    if _rewrite_fixtures():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    changed = ", ".join(_changed_keys(held, events)[:10])
    raise AssertionError(
        f"{path.name} is stale (changed: {changed}). Run `uv run python "
        "scripts/record_ui_cassettes.py`, which rewrites it, and commit the result."
    )


def with_standards(governance: Governance) -> Governance:
    """`governance` with the standards advisor registered as the reference list would reach its
    service, but served in memory over A2A."""
    governance.conductor.registry.add(in_process(standards.build()))
    return governance


def configure_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The app's reference set, a principal, and runs and projects written under `tmp_path`.

    The reference agent list names services these tests do not start, and whether one happens to
    be running would change what the server says, so it is replaced by an empty list. A test
    that needs an agent serves it in memory over A2A (`with_standards`).
    """
    for variable in PATH_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    no_remote_agents = tmp_path / "agents.yaml"
    no_remote_agents.write_text("agents: []\n", encoding="utf-8")
    monkeypatch.setenv("DD_AGENTS_CONFIG", str(no_remote_agents))
    for variable in ("DD_STANDARDS_RETRIEVAL", "DD_SNAPSHOT_PATH"):
        monkeypatch.delenv(variable, raising=False)
    # The standards advisor's model is on by default; these tests run it without one.
    monkeypatch.setenv("DD_STANDARDS_EXPLAINER", "template")
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)
    monkeypatch.setenv("DD_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("DD_PROJECTS_DIR", str(tmp_path / "projects"))
    return tmp_path


def new_governance() -> Iterator[Governance]:
    yield with_standards(Governance.create(settings_from_env(), APP_URL))


def dist_dir(tmp_path: Path) -> Path:
    built = tmp_path / "dist"
    built.mkdir()
    (built / "index.html").write_text("<!doctype html><title>shell</title>", encoding="utf-8")
    return built


# What the route tests share (moved from test_app.py).

STANDARDS_AGENT_ID = "advisor.standards"

EXAMPLES = Path(__file__).resolve().parents[1] / "config/examples"
FIXED_RUN_ID = "01900000-0000-7000-8000-000000000001"
FIXED_TIME = "2026-01-01T00:00:00Z"


def example(name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((EXAMPLES / f"{name}.json").read_text("utf-8"))
    return document


def run(client: TestClient, input: Any, agent_id: str = STANDARDS_AGENT_ID) -> Any:
    return client.post("/api/runs", json={"agent_id": agent_id, "input": input})


def normalised(body: dict[str, Any]) -> dict[str, Any]:
    envelope = body["envelope"]
    envelope["invocation_id"] = FIXED_RUN_ID
    envelope["completed_at"] = FIXED_TIME
    envelope["telemetry"]["trace_id"] = "0" * 32
    for item in envelope.get("evidence") or []:
        item["retrieved_at"] = FIXED_TIME
    return body


UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SHA256 = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})")
TRACE_ID = re.compile(r'"trace_id": "[0-9a-f]{32}"')


def normalised_conversation(body: Any) -> Any:
    """`body` with each identifier and hash that changes between two runs of the same
    conversation replaced by a fixed one, numbered in order of first appearance, so the same
    value stays the same throughout. A turn's input hash covers the history, which names the
    earlier turns' runs, and a delegation's content hash covers the child's envelope, so the
    hashes change with the identifiers."""
    text = json.dumps(body, sort_keys=True)
    seen: dict[str, str] = {}

    def fixed(template: str) -> Any:
        def replace(match: re.Match[str]) -> str:
            value = match.group(0)
            if value not in seen:
                seen[value] = template.format(len(seen) + 1)
            return seen[value]

        return replace

    text = UUID.sub(fixed("01900000-0000-7000-8000-{:012d}"), text)
    text = SHA256.sub(fixed("{:064d}"), text)
    text = TIMESTAMP.sub(FIXED_TIME, text)
    text = TRACE_ID.sub(f'"trace_id": "{"0" * 32}"', text)
    return json.loads(text)


def start(client: TestClient) -> str:
    response = client.post("/api/conversations", headers=JSON_HEADERS)
    assert response.status_code == 201
    conversation_id: str = response.json()["conversation_id"]
    assert response.headers["location"] == f"/api/conversations/{conversation_id}"
    return conversation_id


def turn(
    client: TestClient,
    conversation_id: str,
    text: str,
    follows: str | None = None,
    **extra: Any,
) -> Any:
    return client.post(
        f"/api/conversations/{conversation_id}/turns",
        json={"agent_id": "orchestrator.stub", "message_text": text, "follows": follows, **extra},
    )


def a_file_inventory(*paths: str) -> dict[str, Any]:
    """What `dd-inventory` writes for files at `paths`."""
    return {
        "schema_class": "FileInventory",
        "inventory_tool": "dd-inventory",
        "inventory_tool_version": "0.1.0",
        "inventory_made_at": "2026-11-01T09:00:00Z",
        "inventory_files": [
            {
                "file_path": path,
                "file_size": 10,
                "file_sha256": "a" * 64,
                "file_media_type": "text/csv",
                "file_identified_by": "extension",
            }
            for path in paths
        ],
    }


PROTOCOL = "# Sampling protocol\n\nSediment cores were taken monthly from three sites.\n"


def a_document(text: str = PROTOCOL, name: str = "protocol.md") -> dict[str, str]:
    return {"name": name, "media_type": "text/markdown", "text": text}


OTHER = TEST_PRINCIPAL.model_copy(
    update={"principal_id": "https://orcid.org/0000-0001-5000-0007", "name": "Ada Example"}
)


def delegating_app(env: Path, dist: Path, projects: ProjectStore | None) -> tuple[Governance, Any]:
    served: dict[str, Any] = {}

    def app_client(base_url: str, timeout_s: float) -> httpx.AsyncClient:
        return asgi_client_factory(served["app"])(base_url, timeout_s)

    registry = Registry.from_agents(
        [
            in_process(build_director(), delegate_client_factory=app_client),
            in_process(build_hello()),
        ]
    )
    conductor = Conductor(
        registry=registry, store=RunStore(env), profile=load_profile(DEFAULT_PROFILE)
    )
    conductor.harness_url = APP_URL
    governance = Governance(conductor, OperatorAssertion(TEST_PRINCIPAL), projects)
    served["app"] = build_app(governance, dist)
    return governance, served["app"]

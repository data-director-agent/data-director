"""The `workbench` CLI: a missing or malformed configuration file is one line, not a traceback;
`agents` lists the registry; `verify` re-runs the source check; and nothing runs without a
principal (ADR-0018)."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from dd_agent_factcheck.agent import FactChecker
from dd_agent_hello.agent import HelloWorld
from dd_agent_quality.agent import QualityReviewer
from dd_agent_stub.agent import AbstainingStub
from dd_harness.registry import Registry
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk import serve
from dd_sdk.agent import Agent
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash
from workbench import cli

INVOKE = ["invoke", "--agent", "hello.world", "--input", "samples/hello.salutation.json"]


@pytest.fixture(autouse=True)
def principal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)
    monkeypatch.setenv("DD_RUNS_DIR", str(tmp_path / "runs"))
    # No agents, so the CLI reaches the profile and sources without fetching a card.
    agents = tmp_path / "agents.yaml"
    agents.write_text("agents: []\n", encoding="utf-8")
    monkeypatch.setenv("DD_AGENTS_CONFIG", str(agents))


@pytest.mark.parametrize(
    ("variable", "command", "message"),
    [
        ("DD_PROFILE", INVOKE, "profile not found at"),
        ("DD_SOURCES_CONFIG", INVOKE, "cannot read"),
        ("DD_AGENTS_CONFIG", ["agents"], "agent configuration .* not found"),
    ],
)
def test_a_missing_configuration_file_is_a_one_line_error(
    variable: str,
    command: list[str],
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(variable, str(tmp_path / "nonexistent.yaml"))
    with pytest.raises(SystemExit, match=f"^workbench: {message}"):
        cli.main(command)


# --- agents -----------------------------------------------------------------------------------

AGENTS: dict[str, Agent] = {
    "http://hello.test": HelloWorld(),
    "http://quality.test": QualityReviewer(),
    "http://factcheck.test": FactChecker(),
    "http://stub.test": AbstainingStub(),
}
IDS = {"fact.checker", "hello.world", "quality.reviewer", "stub.abstain"}


def _registry(tmp_path: Path) -> Registry:
    """The four agents above, served in memory, and an `standards` entry nothing answers."""
    apps = {url: serve.app(agent, base_url=url) for url, agent in AGENTS.items()}

    def factory(base_url: str, timeout_s: float) -> httpx.AsyncClient:
        if base_url not in apps:
            raise httpx.ConnectError(f"connection refused: {base_url}")
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=apps[base_url]), base_url=base_url, timeout=timeout_s
        )

    entries = [{"url": url} for url in AGENTS] + [
        {"name": "standards", "url": "http://standards.test"}
    ]
    config = tmp_path / "listed.yaml"
    config.write_text(json.dumps({"agents": entries}), encoding="utf-8")  # JSON is YAML
    return Registry.from_config(config, client_factory=factory)


@pytest.mark.requirement("DD-REGISTRY")
def test_agents_command_lists_the_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = _registry(tmp_path)
    monkeypatch.setattr(cli, "build_registry", lambda settings: registry)
    assert cli.main(["agents"]) == 0
    out = capsys.readouterr().out
    for agent_id in IDS:
        assert agent_id in out
    assert "input_only" in out and "[standards] unavailable" in out
    assert cli.main(["agents", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {m["agent_id"] for m in data["agents"]} == IDS and "standards" in data["unavailable"]
    assert data["incompatible"] == {}


# --- verify -----------------------------------------------------------------------------------

SNAPSHOT_REF = "test:records"
RECORD = {"source_id": "src:a", "text": "Alpha."}


def _envelope(document: dict[str, Any]) -> dict[str, Any]:
    evidence = {
        "source_id": "src:a",
        "snapshot_ref": SNAPSHOT_REF,
        "canonicalisation": DOCUMENT_CANONICALISATION,
        "content_hash": content_hash(document, DOCUMENT_CANONICALISATION),
        "content": document,
    }
    return {"grounding_mode": "retrieval", "evidence": [evidence]}


@pytest.mark.requirement("DD-EVIDENCE")
def test_verify_exits_non_zero_on_a_violation(tmp_path: Path, capsys: Any) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text(json.dumps(RECORD) + "\n", encoding="utf-8")
    pin = hashlib.sha256(path.read_bytes()).hexdigest()
    config = tmp_path / "sources.yaml"
    config.write_text(
        f"sources:\n  - snapshot_refs: [{SNAPSHOT_REF}]\n    path: {path.name}\n"
        f"    id_field: source_id\n    sha256: {pin}\n",
        encoding="utf-8",
    )
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(_envelope(RECORD)), encoding="utf-8")
    altered = {"source_id": "src:a", "text": "Alpha, revised."}
    bad.write_text(json.dumps(_envelope(altered)), encoding="utf-8")
    assert cli.main(["verify", str(good), "--sources", str(config)]) == 0
    assert cli.main(["verify", str(bad), "--sources", str(config)]) == 1
    assert "S2:" in capsys.readouterr().out


# --- Whom an invocation acts for (ADR-0018) ---------------------------------------------------


@pytest.fixture
def no_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("DD_PRINCIPAL_ID", "DD_PRINCIPAL_NAME", "DD_PRINCIPAL_KIND"):
        monkeypatch.delenv(variable, raising=False)


@pytest.mark.requirement("DD-ACTS-FOR")
@pytest.mark.parametrize(
    "command", [["invoke", "--agent", "hello.world", "--input", "samples/claim.json"], ["serve"]]
)
def test_the_cli_runs_nothing_without_a_principal(
    no_principal: None, command: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = tmp_path / "runs-unused"
    runs.mkdir()
    monkeypatch.setenv("DD_RUNS_DIR", str(runs))
    with pytest.raises(SystemExit, match="DD_PRINCIPAL_ID and DD_PRINCIPAL_NAME unset"):
        cli.main(command)
    assert list(runs.iterdir()) == []


def test_the_cli_flags_replace_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DD_PRINCIPAL_ID", "urn:example:someone")
    monkeypatch.setenv("DD_PRINCIPAL_NAME", "Someone")
    args = argparse.Namespace(
        profile=None, acting_for_id=TEST_PRINCIPAL.principal_id, acting_for_name=TEST_PRINCIPAL.name
    )
    assert cli._settings(args).principal() == TEST_PRINCIPAL

"""The CLI reports a missing or malformed configuration file in one line, not a traceback."""

from __future__ import annotations

from pathlib import Path

import pytest

from workbench import cli
from workbench.testing import TEST_PRINCIPAL

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

"""The development set-up in scripts/dev.py and scripts/devstack/: where `setup` writes each
setting, and the checks `start` and `doctor` make before running anything."""

from __future__ import annotations

import os
import re
import shutil
import stat
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from devstack import common, paths  # noqa: E402
from devstack.setup import Prompter, mask, setup  # noqa: E402

KEY = "sk-ant-test-0123456789abcd"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository root holding only what dev.py reads, with its paths pointed at it."""
    config = tmp_path / "app" / "config"
    config.mkdir(parents=True)
    (config / "profile.yaml.example").write_text(
        (ROOT / "app" / "config" / "profile.yaml.example").read_text(encoding="utf-8")
    )
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    shutil.copytree(ROOT / "config" / "examples", tmp_path / "config" / "examples")
    local = tmp_path / "config" / "local"
    monkeypatch.setattr(paths, "LOCAL_DIR", local)
    monkeypatch.setattr(paths, "EXAMPLES_DIR", tmp_path / "config" / "examples")
    monkeypatch.setattr(paths, "APP_ENV", local / "app.env")
    monkeypatch.setattr(paths, "AGENTS_ENV", local / "agents.env")
    monkeypatch.setattr(paths, "AGENT_ENV_DIR", local / "agents")
    monkeypatch.setattr(paths, "CREDENTIALS_DIR", local / "credentials")
    monkeypatch.setattr(paths, "PROFILE_EXAMPLE", config / "profile.yaml.example")
    monkeypatch.setattr(paths, "PROFILE", config / "profile.yaml")
    return tmp_path


def scripted(*answers: str, asked: list[str] | None = None) -> Prompter:
    """A prompter that gives `answers` in order, to questions and secrets alike, and records each
    question in `asked`."""
    queue: Iterator[str] = iter(answers)
    log = [] if asked is None else asked

    def answer(question: str) -> str:
        log.append(question)
        return next(queue)

    return Prompter(ask=answer, ask_secret=answer)


def test_defaults_write_the_example_principal_and_no_key(repo: Path) -> None:
    assert setup(Prompter(accept_defaults=True), install=False) == 0
    assert common.read_env(repo / "config" / "local" / "app.env") == common.EXAMPLE_PRINCIPAL
    assert (repo / "config" / "local" / "agents.env").is_file()
    assert not list((repo / "config" / "local" / "agents").iterdir())
    assert not list((repo / "config" / "local" / "credentials").iterdir())
    assert not (repo / "app" / "config" / "profile.yaml").exists()


def test_a_bare_orcid_id_is_given_its_prefix_and_a_name_with_a_space_is_quoted(
    repo: Path,
) -> None:
    setup(scripted("Ada Lovelace", "0000-0001-2345-678X", "", ""), install=False)
    text = (repo / "config" / "local" / "app.env").read_text()
    assert 'DD_PRINCIPAL_NAME="Ada Lovelace"' in text
    assert (
        common.read_env(repo / "config" / "local" / "app.env")["DD_PRINCIPAL_ID"]
        == "https://orcid.org/0000-0001-2345-678X"
    )


def test_an_invalid_id_is_asked_again(repo: Path) -> None:
    setup(scripted("Ada", "not an id", "https://ror.org/05krs5044", "", ""), install=False)
    app = common.read_env(repo / "config" / "local" / "app.env")
    assert app["DD_PRINCIPAL_ID"] == "https://ror.org/05krs5044"


def test_the_key_goes_only_to_the_agents_that_use_it(repo: Path) -> None:
    setup(scripted("", "", KEY, "y", "y", ""), install=False)
    local = repo / "config" / "local"
    agents, credentials = local / "agents", local / "credentials"
    assert common.read_env(agents / "orchestrator.env") == {
        "ANTHROPIC_API_KEY_FILE": "orchestrator-anthropic-api-key"
    }
    assert common.read_env(agents / "standards.env") == {
        "DD_STANDARDS_EXPLAINER": "anthropic",
        "ANTHROPIC_API_KEY_FILE": "standards-anthropic-api-key",
    }
    assert (credentials / "orchestrator-anthropic-api-key").read_text().strip() == KEY
    assert (credentials / "standards-anthropic-api-key").read_text().strip() == KEY
    for path in (local / "app.env", local / "agents.env", agents / "orchestrator.env"):
        assert KEY not in path.read_text()
    for path in (*credentials.iterdir(), agents / "orchestrator.env", local / "app.env"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_key_makes_the_model_orchestrator_the_home_pages_with_a_new_version(repo: Path) -> None:
    setup(scripted("", "", KEY, "n", "y", ""), install=False)
    profile = (repo / "app" / "config" / "profile.yaml").read_text()
    example = (repo / "app" / "config" / "profile.yaml.example").read_text()
    assert "\norchestrator: orchestrator.model\n" in profile
    found = re.search(r"^version: (\d+)", example, re.MULTILINE)
    assert found
    old = int(found[1])
    assert f"\nversion: {old + 1}\n" in profile
    # A second run finds it already named and leaves the version alone.
    setup(scripted("", "", "", "n", "y", ""), install=False)
    assert (repo / "app" / "config" / "profile.yaml").read_text() == profile


def test_a_rerun_keeps_the_key_and_other_lines(repo: Path) -> None:
    local = repo / "config" / "local"
    own = local / "agents" / "orchestrator.env"
    own.parent.mkdir(parents=True)
    text = (
        "# mine\nDD_MODEL_ID=claude-haiku-5-5\n"
        "ANTHROPIC_API_KEY_FILE=orchestrator-anthropic-api-key\n"
    )
    own.write_text(text)
    (local / "credentials").mkdir()
    (local / "credentials" / "orchestrator-anthropic-api-key").write_text(KEY + "\n")
    asked: list[str] = []
    setup(scripted("", "", "", "n", "n", "", asked=asked), install=False)
    assert own.read_text() == text
    assert any(mask(KEY) in q for q in asked) and not any(KEY in q for q in asked)


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("DD_PRINCIPAL_NAME=Josiah Carberry\n", "put quotes round"),
        ("DD_PRINCIPAL_NAME\n", "expected NAME=value"),
        ('DD_PRINCIPAL_NAME="Josiah\n', "not closed"),
    ],
)
def test_a_malformed_settings_file_names_its_line(text: str, fragment: str) -> None:
    with pytest.raises(common.DevError, match=fragment):
        common.parse_env(text, "x.env")


def test_settings_files_read_as_uv_reads_them() -> None:
    text = "# c\nexport A=1\nB='two words'\nC=\"x\" # note\nD=plain # note\n\n"
    assert common.parse_env(text) == {"A": "1", "B": "two words", "C": "x", "D": "plain"}


def test_a_fairsharing_login_turns_on_live_search_in_the_files_of_the_agents_that_search(
    repo: Path,
) -> None:
    setup(scripted("", "", "", "ada", "s3cret"), install=False)
    local = repo / "config" / "local"
    for agent, switch in (
        ("standards", "DD_STANDARDS_RETRIEVAL"),
        ("policy", "DD_POLICY_RETRIEVAL"),
    ):
        own = local / "agents" / f"{agent}.env"
        assert common.read_env(own) == {
            switch: "live",
            "FAIRSHARING_LOGIN": "ada",
            "FAIRSHARING_PASSWORD": "s3cret",
        }
        assert stat.S_IMODE(own.stat().st_mode) == 0o600
    for other in (local / "app.env", local / "agents.env"):
        assert "s3cret" not in other.read_text()
    # A rerun keeps the password when Enter is pressed.
    asked: list[str] = []
    setup(scripted("", "", "", "", "", asked=asked), install=False)
    assert common.read_env(local / "agents" / "standards.env")["FAIRSHARING_PASSWORD"] == "s3cret"
    assert common.read_env(local / "agents" / "policy.env")["FAIRSHARING_PASSWORD"] == "s3cret"
    assert any(mask("s3cret") in q for q in asked) and not any("s3cret" in q for q in asked)


def test_a_key_in_a_shared_file_is_refused(repo: Path) -> None:
    local = repo / "config" / "local"
    local.mkdir(parents=True)
    (local / "agents.env").write_text(f"ANTHROPIC_API_KEY={KEY}\n")
    with pytest.raises(common.DevError, match="ADR-0026"):
        common.agent_env(common.Agent("hello", 8101))


def test_an_agent_reads_its_own_file_and_the_shared_one_but_not_the_apps_or_anothers(
    repo: Path,
) -> None:
    local = repo / "config" / "local"
    common.ensure_local_tree()
    (local / "app.env").write_text("DD_PRINCIPAL_NAME=Ada\n")
    (local / "agents.env").write_text("DD_MODEL_ID=shared\nDD_OTHER=1\n")
    (local / "agents" / "orchestrator.env").write_text("DD_MODEL_ID=own\nANTHROPIC_API_KEY=k\n")
    (local / "agents" / "standards.env").write_text("DD_STANDARDS_EXPLAINER=anthropic\n")
    env = common.agent_env(common.Agent("orchestrator", 8107))
    assert env["DD_MODEL_ID"] == "own" and env["DD_OTHER"] == "1"
    assert "DD_PRINCIPAL_NAME" not in env and "DD_STANDARDS_EXPLAINER" not in env
    assert env["CREDENTIALS_DIRECTORY"] == str(local / "credentials")
    assert "ANTHROPIC_API_KEY" not in common.agent_env(common.Agent("standards", 8105))
    assert common.app_env() == {"DD_PRINCIPAL_NAME": "Ada"}
    assert "DD_MODEL_ID" not in common.app_env()


def test_the_tree_is_made_from_the_examples_and_never_overwritten(repo: Path) -> None:
    created = common.ensure_local_tree()
    assert {p.name for p in created} == {"app.env", "agents.env"}
    (repo / "config" / "local" / "app.env").write_text("DD_PRINCIPAL_NAME=mine\n")
    assert common.ensure_local_tree() == []
    assert common.read_env(repo / "config" / "local" / "app.env") == {"DD_PRINCIPAL_NAME": "mine"}


def test_settings_files_of_the_old_layout_are_reported_with_where_they_move(repo: Path) -> None:
    (repo / ".env").write_text("DD_PRINCIPAL_NAME=x\n")
    (repo / "workbench" / "agents").mkdir(parents=True)
    (repo / "workbench" / "agents" / "orchestrator.env").write_text("ANTHROPIC_API_KEY=k\n")
    found = common.stray_files()
    assert any(f.startswith(".env -> config/local/app.env") for f in found)
    assert any(
        "workbench/agents/orchestrator.env -> config/local/agents/orchestrator.env" in f
        for f in found
    )


def test_the_agents_and_ports_come_from_the_apps_list() -> None:
    agents = common.load_agents(ROOT / "app" / "config" / "agents.yaml")
    assert {a.script: a.port for a in agents}["dd-hello"] == 8101
    assert all(
        a.name
        in {"hello", "quality", "standards", "policy", "repository", "director", "orchestrator"}
        for a in agents
    )


def test_the_shell_is_rebuilt_when_its_source_is_newer(tmp_path: Path) -> None:
    web = tmp_path
    (web / "src").mkdir()
    (web / "src" / "main.tsx").write_text("")
    (web / "package-lock.json").write_text("{}")
    assert common.needs_install(web) and common.needs_build(web)

    (web / "node_modules").mkdir()
    (web / "dist").mkdir()
    (web / "dist" / "index.html").write_text("")
    assert not common.needs_install(web) and not common.needs_build(web)

    later = time.time() + 10
    os.utime(web / "src" / "main.tsx", (later, later))
    assert common.needs_build(web) and not common.needs_install(web)

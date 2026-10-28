"""The development set-up in scripts/dev.py: where `setup` writes each setting, and the checks
`start` and `doctor` make before running anything."""

from __future__ import annotations

import os
import re
import stat
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import dev  # noqa: E402

KEY = "sk-ant-test-0123456789abcd"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository root holding only what dev.py reads, with its paths pointed at it."""
    config = tmp_path / "app" / "config"
    config.mkdir(parents=True)
    (config / "profile.yaml.example").write_text(
        (ROOT / "app" / "config" / "profile.yaml.example").read_text(encoding="utf-8")
    )
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setattr(dev, "ROOT_ENV", tmp_path / ".env")
    monkeypatch.setattr(dev, "WORKBENCH_ENV", tmp_path / "workbench" / ".env")
    monkeypatch.setattr(dev, "AGENT_ENV_DIR", tmp_path / "workbench" / "agents")
    monkeypatch.setattr(dev, "PROFILE_EXAMPLE", config / "profile.yaml.example")
    monkeypatch.setattr(dev, "PROFILE", config / "profile.yaml")
    return tmp_path


def scripted(*answers: str, asked: list[str] | None = None) -> dev.Prompter:
    """A prompter that gives `answers` in order, to questions and secrets alike, and records each
    question in `asked`."""
    queue: Iterator[str] = iter(answers)
    log = [] if asked is None else asked

    def answer(question: str) -> str:
        log.append(question)
        return next(queue)

    return dev.Prompter(ask=answer, ask_secret=answer)


def test_defaults_write_the_example_principal_and_no_key(repo: Path) -> None:
    assert dev.setup(dev.Prompter(accept_defaults=True), install=False) == 0
    assert dev.read_env(repo / ".env") == dev.EXAMPLE_PRINCIPAL
    assert not (repo / "workbench" / "agents").exists()
    assert not (repo / "app" / "config" / "profile.yaml").exists()


def test_a_bare_orcid_id_is_given_its_prefix_and_a_name_with_a_space_is_quoted(
    repo: Path,
) -> None:
    dev.setup(scripted("Ada Lovelace", "0000-0001-2345-678X", ""), install=False)
    text = (repo / ".env").read_text()
    assert 'DD_PRINCIPAL_NAME="Ada Lovelace"' in text
    assert dev.read_env(repo / ".env")["DD_PRINCIPAL_ID"] == "https://orcid.org/0000-0001-2345-678X"


def test_an_invalid_id_is_asked_again(repo: Path) -> None:
    dev.setup(scripted("Ada", "not an id", "https://ror.org/05krs5044", ""), install=False)
    assert dev.read_env(repo / ".env")["DD_PRINCIPAL_ID"] == "https://ror.org/05krs5044"


def test_the_key_goes_only_to_the_agents_that_use_it(repo: Path) -> None:
    dev.setup(scripted("", "", KEY, "y", "y"), install=False)
    agents = repo / "workbench" / "agents"
    assert dev.read_env(agents / "orchestrator.env") == {"ANTHROPIC_API_KEY": KEY}
    assert dev.read_env(agents / "standards.env") == {
        "DD_STANDARDS_EXPLAINER": "anthropic",
        "ANTHROPIC_API_KEY": KEY,
    }
    assert KEY not in (repo / ".env").read_text()
    for path in (agents / "orchestrator.env", agents / "standards.env", repo / ".env"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_key_makes_the_model_orchestrator_the_home_pages_with_a_new_version(repo: Path) -> None:
    dev.setup(scripted("", "", KEY, "n", "y"), install=False)
    profile = (repo / "app" / "config" / "profile.yaml").read_text()
    example = (repo / "app" / "config" / "profile.yaml.example").read_text()
    assert "\norchestrator: orchestrator.model\n" in profile
    found = re.search(r"^version: (\d+)", example, re.MULTILINE)
    assert found
    old = int(found[1])
    assert f"\nversion: {old + 1}\n" in profile
    # A second run finds it already named and leaves the version alone.
    dev.setup(scripted("", "", "", "n", "y"), install=False)
    assert (repo / "app" / "config" / "profile.yaml").read_text() == profile


def test_a_rerun_keeps_the_key_and_other_lines(repo: Path) -> None:
    own = repo / "workbench" / "agents" / "orchestrator.env"
    own.parent.mkdir(parents=True)
    own.write_text(f"# mine\nDD_MODEL_ID=claude-haiku-5-5\nANTHROPIC_API_KEY={KEY}\n")
    asked: list[str] = []
    dev.setup(scripted("", "", "", "n", "n", asked=asked), install=False)
    assert own.read_text() == f"# mine\nDD_MODEL_ID=claude-haiku-5-5\nANTHROPIC_API_KEY={KEY}\n"
    assert any(dev.mask(KEY) in q for q in asked) and not any(KEY in q for q in asked)


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("DD_PRINCIPAL_NAME=Josiah Carberry\n", "put quotes round"),
        ("DD_PRINCIPAL_NAME\n", "expected NAME=value"),
        ('DD_PRINCIPAL_NAME="Josiah\n', "not closed"),
    ],
)
def test_a_malformed_settings_file_names_its_line(text: str, fragment: str) -> None:
    with pytest.raises(dev.DevError, match=fragment):
        dev.parse_env(text, "x.env")


def test_settings_files_read_as_uv_reads_them() -> None:
    text = "# c\nexport A=1\nB='two words'\nC=\"x\" # note\nD=plain # note\n\n"
    assert dev.parse_env(text) == {"A": "1", "B": "two words", "C": "x", "D": "plain"}


def test_a_key_in_a_shared_file_is_refused(repo: Path) -> None:
    (repo / ".env").write_text(f"ANTHROPIC_API_KEY={KEY}\n")
    with pytest.raises(dev.DevError, match="ADR-0026"):
        dev.shared_env()


def test_the_root_env_wins_over_the_workbench_one(repo: Path) -> None:
    (repo / "workbench").mkdir()
    (repo / "workbench" / ".env").write_text("DD_PRINCIPAL_NAME=old\nDD_RUNS_DIR=runs\n")
    (repo / ".env").write_text("DD_PRINCIPAL_NAME=new\n")
    assert dev.shared_env() == {"DD_PRINCIPAL_NAME": "new", "DD_RUNS_DIR": "runs"}


def test_the_agents_and_ports_come_from_the_apps_list() -> None:
    agents = dev.load_agents(ROOT / "app" / "config" / "agents.yaml")
    assert {a.script: a.port for a in agents}["dd-hello"] == 8101
    assert all(
        a.name in {"hello", "quality", "standards", "director", "orchestrator"} for a in agents
    )


def test_the_shell_is_rebuilt_when_its_source_is_newer(tmp_path: Path) -> None:
    web = tmp_path
    (web / "src").mkdir()
    (web / "src" / "main.tsx").write_text("")
    (web / "package-lock.json").write_text("{}")
    assert dev.needs_install(web) and dev.needs_build(web)

    (web / "node_modules").mkdir()
    (web / "dist").mkdir()
    (web / "dist" / "index.html").write_text("")
    assert not dev.needs_install(web) and not dev.needs_build(web)

    later = time.time() + 10
    os.utime(web / "src" / "main.tsx", (later, later))
    assert dev.needs_build(web) and not dev.needs_install(web)

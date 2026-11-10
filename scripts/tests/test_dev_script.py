"""The development set-up in scripts/dd.py and scripts/ddtool/: where `setup` writes each
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
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import dd  # noqa: E402
from ddtool import (  # noqa: E402
    common,
    paths,
    secret,
)
from ddtool.setup import DB_LOCATION, Prompter, mask, setup  # noqa: E402

KEY = "sk-ant-test-0123456789abcd"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository root holding only what dd.py reads, with its paths pointed at it."""
    config = tmp_path / "app" / "config"
    config.mkdir(parents=True)
    for name in ("profile.yaml.example", "agents.yaml"):
        shutil.copyfile(ROOT / "app" / "config" / name, config / name)
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "AGENTS_CONFIG", config / "agents.yaml")
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
    """A prompter that gives `answers` in order, to questions and secrets alike, then presses Enter
    to each question after them, and records each question in `asked`."""
    queue: Iterator[str] = iter(answers)
    log = [] if asked is None else asked

    def answer(question: str) -> str:
        log.append(question)
        return next(queue, "")

    return Prompter(ask=answer, ask_secret=answer)


def test_defaults_write_the_example_principal_and_no_key(repo: Path) -> None:
    assert setup(Prompter(accept_defaults=True), install=False) == 0
    local = repo / "config" / "local"
    assert common.read_env(local / "app.env") == common.EXAMPLE_PRINCIPAL | {
        "DD_PROFILE": str(local / "profile.yaml")
    }
    assert (local / "agents.env").is_file()
    assert not list((local / "agents").iterdir())
    assert not list((local / "credentials").iterdir())
    assert not (repo / "app" / "config" / "profile.yaml").exists()
    # The profile is generated from deployment.yaml, with the rule-based orchestrator.
    assert "\norchestrator: stub\n" in (local / "deployment.yaml").read_text()
    assert "\norchestrator: orchestrator.stub\n" in (local / "profile.yaml").read_text()


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
    assert common.read_env(agents / "orchestrator-model.env") == {
        "ANTHROPIC_API_KEY_FILE": "orchestrator-model-anthropic-api-key"
    }
    assert common.read_env(agents / "advisor-standards.env") == {
        "DD_STANDARDS_EXPLAINER": "anthropic",
        "ANTHROPIC_API_KEY_FILE": "advisor-standards-anthropic-api-key",
    }
    assert (credentials / "orchestrator-model-anthropic-api-key").read_text().strip() == KEY
    assert (credentials / "advisor-standards-anthropic-api-key").read_text().strip() == KEY
    for path in (local / "app.env", local / "agents.env", agents / "orchestrator-model.env"):
        assert KEY not in path.read_text()
    for path in (*credentials.iterdir(), agents / "orchestrator-model.env", local / "app.env"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_key_makes_the_model_orchestrator_the_home_pages_with_a_new_version(repo: Path) -> None:
    setup(scripted("", "", KEY, "n", "y", ""), install=False)
    local = repo / "config" / "local"
    assert "\norchestrator: model\n" in (local / "deployment.yaml").read_text()
    profile = (local / "profile.yaml").read_text()
    example = (repo / "app" / "config" / "profile.yaml.example").read_text()
    assert "\norchestrator: orchestrator.model\n" in profile
    # What may go to a hosted model is the example's (docs/specs/projects.md, invariant 8).
    assert "\nhosted_models:\n- inventory\n- documentation\n" in profile
    found = re.search(r"^version: (\d+)", example, re.MULTILINE)
    assert found
    old = int(found[1])
    assert f"\nversion: {old + 1}\n" in profile
    # A second run finds it already named and leaves the version alone.
    setup(scripted("", "", "", "n", "y", ""), install=False)
    assert (local / "profile.yaml").read_text() == profile


def test_a_local_profile_missing_an_agent_the_example_enables_is_reported(repo: Path) -> None:
    config = repo / "app" / "config"
    assert common.profile_omissions({}) == []  # no local copy: the app uses the example
    example = (config / "profile.yaml.example").read_text()
    stale = yaml.safe_load(example)
    dropped = sorted(stale["agents"])[:2]
    for name in dropped:
        del stale["agents"][name]
    (config / "profile.yaml").write_text(yaml.safe_dump(stale))
    omitted = common.profile_omissions({})
    assert omitted == dropped
    note = common.omissions_note(omitted)
    assert "app/config/profile.yaml" in note and all(name in note for name in dropped)
    # A profile chosen with DD_PROFILE is the deployment's choice, and is not compared.
    assert common.profile_omissions({"DD_PROFILE": str(config / "profile.yaml")}) == []
    (config / "profile.yaml").write_text(example)
    assert common.profile_omissions({}) == []


def test_a_local_profile_that_has_fallen_behind_the_example_is_reported(repo: Path) -> None:
    config = repo / "app" / "config"
    example = (config / "profile.yaml.example").read_text()
    local = config / "profile.yaml"
    assert common.profile_drift({}) == ([], [])  # no local copy: the app uses the example
    local.write_text(example)
    assert common.profile_drift({}) == ([], [])
    version = int(re.search(r"^version: (\d+)", example, re.MULTILINE)[1])  # type: ignore[index]
    # Older than the example, and requiring approval for less.
    stale = example.replace(f"version: {version}\n", f"version: {version - 1}\n").replace(
        "  - deposit\n", ""
    )
    assert stale != example
    local.write_text(stale)
    notes, problems = common.profile_drift({})
    assert problems == []
    assert any(f"is version {version - 1}, behind the example's {version}" in n for n in notes)
    assert any("does not require approval for deposit" in n for n in notes)
    # Newer than the example, as `setup` leaves it, is not drift.
    local.write_text(example.replace(f"version: {version}\n", f"version: {version + 1}\n"))
    assert common.profile_drift({}) == ([], [])
    # An orchestrator the profile does not enable is a problem.
    local.write_text(example.replace("orchestrator: orchestrator.stub", "orchestrator: nobody"))
    assert common.profile_drift({})[1] == [
        "app/config/profile.yaml names nobody as the orchestrator but does not enable it"
    ]
    # A profile chosen with DD_PROFILE is the deployment's choice, and is not compared.
    assert common.profile_drift({"DD_PROFILE": str(local)}) == ([], [])


def test_a_rerun_keeps_the_key_and_other_lines(repo: Path) -> None:
    local = repo / "config" / "local"
    own = local / "agents" / "orchestrator-model.env"
    own.parent.mkdir(parents=True)
    text = (
        "# mine\nDD_MODEL_ID=claude-haiku-5-5\n"
        "ANTHROPIC_API_KEY_FILE=orchestrator-model-anthropic-api-key\n"
    )
    own.write_text(text)
    (local / "credentials").mkdir()
    (local / "credentials" / "orchestrator-model-anthropic-api-key").write_text(KEY + "\n")
    asked: list[str] = []
    setup(scripted("", "", "", "n", "n", "", asked=asked), install=False)
    assert own.read_text() == text
    assert any(mask(KEY) in q for q in asked) and not any(KEY in q for q in asked)


def test_runs_and_projects_stay_in_files_by_default(repo: Path) -> None:
    setup(Prompter(accept_defaults=True), install=False)
    app = common.read_env(repo / "config" / "local" / "app.env")
    assert not {"DD_RUNS_DIR", "DD_PROJECTS_DIR", "PGPASSFILE"} & app.keys()
    assert not (repo / "config" / "local" / "credentials" / "pgpass").exists()


def test_postgresql_gets_a_password_file_and_locations_without_a_password(repo: Path) -> None:
    # Principal, model key, FAIRsharing login, then PostgreSQL.
    setup(scripted("", "", "", "", "y"), install=False)
    local = repo / "config" / "local"
    credentials = local / "credentials"
    password = (credentials / "postgres-password").read_text().strip()
    assert len(password) >= 32
    assert (credentials / "pgpass").read_text() == f"*:*:dd:dd:{password}\n"
    for path in (credentials / "postgres-password", credentials / "pgpass", local / "app.env"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    app = common.read_env(local / "app.env")
    assert app["DD_RUNS_DIR"] == app["DD_PROJECTS_DIR"] == DB_LOCATION == "postgresql://dd@/dd"
    assert (app["PGHOST"], app["PGPORT"]) == ("localhost", "5432")
    assert app["PGPASSFILE"] == str(credentials / "pgpass")
    assert password not in (local / "app.env").read_text()

    # A rerun asks with yes as the default, and keeps the password the database started with.
    asked: list[str] = []
    setup(scripted(asked=asked), install=False)
    assert any("PostgreSQL" in q and "[Y/n]" in q for q in asked)
    assert (credentials / "postgres-password").read_text().strip() == password
    assert common.read_env(local / "app.env")["DD_RUNS_DIR"] == DB_LOCATION

    # No puts the app back on files, and keeps the password for the volume.
    setup(scripted("", "", "", "", "n"), install=False)
    app = common.read_env(local / "app.env")
    assert not {"DD_RUNS_DIR", "DD_PROJECTS_DIR", "PGHOST", "PGPORT", "PGPASSFILE"} & app.keys()
    assert app["DD_PRINCIPAL_ID"] == common.EXAMPLE_PRINCIPAL["DD_PRINCIPAL_ID"]
    assert (credentials / "postgres-password").read_text().strip() == password


def test_removing_settings_keeps_comments_and_other_lines(tmp_path: Path) -> None:
    path = tmp_path / "app.env"
    path.write_text("# DD_RUNS_DIR=/old\nA=1\nexport DD_RUNS_DIR=x\nB=2\n")
    assert common.remove_env(path, ["DD_RUNS_DIR"])
    assert path.read_text() == "# DD_RUNS_DIR=/old\nA=1\nB=2\n"
    assert not common.remove_env(path, ["DD_RUNS_DIR"])
    assert not common.remove_env(tmp_path / "missing.env", ["A"])


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
        ("advisor-standards", "DD_STANDARDS_RETRIEVAL"),
        ("advisor-policy", "DD_POLICY_RETRIEVAL"),
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
    assert (
        common.read_env(local / "agents" / "advisor-standards.env")["FAIRSHARING_PASSWORD"]
        == "s3cret"
    )
    assert (
        common.read_env(local / "agents" / "advisor-policy.env")["FAIRSHARING_PASSWORD"] == "s3cret"
    )
    assert any(mask("s3cret") in q for q in asked) and not any("s3cret" in q for q in asked)


def test_a_key_in_a_shared_file_is_refused(repo: Path) -> None:
    local = repo / "config" / "local"
    local.mkdir(parents=True)
    (local / "agents.env").write_text(f"ANTHROPIC_API_KEY={KEY}\n")
    with pytest.raises(common.DevError, match=r"docs/specs/policy-and-identity\.md"):
        common.agent_env(common.Agent("example-hello", 8101))


def test_an_agent_reads_its_own_file_and_the_shared_one_but_not_the_apps_or_anothers(
    repo: Path,
) -> None:
    local = repo / "config" / "local"
    common.ensure_local_tree()
    (local / "app.env").write_text("DD_PRINCIPAL_NAME=Ada\n")
    (local / "agents.env").write_text("DD_MODEL_ID=shared\nDD_OTHER=1\n")
    (local / "agents" / "orchestrator-model.env").write_text(
        "DD_MODEL_ID=own\nANTHROPIC_API_KEY=k\n"
    )
    (local / "agents" / "advisor-standards.env").write_text("DD_STANDARDS_EXPLAINER=anthropic\n")
    env = common.agent_env(common.Agent("orchestrator-model", 8107))
    assert env["DD_MODEL_ID"] == "own" and env["DD_OTHER"] == "1"
    assert "DD_PRINCIPAL_NAME" not in env and "DD_STANDARDS_EXPLAINER" not in env
    assert env["CREDENTIALS_DIRECTORY"] == str(local / "credentials")
    assert "ANTHROPIC_API_KEY" not in common.agent_env(common.Agent("advisor-standards", 8105))
    assert common.app_env() == {"DD_PRINCIPAL_NAME": "Ada"}
    assert "DD_MODEL_ID" not in common.app_env()


def test_the_tree_is_made_from_the_examples_and_never_overwritten(repo: Path) -> None:
    created = common.ensure_local_tree()
    assert {p.name for p in created} == {"app.env", "agents.env", "deployment.yaml"}
    (repo / "config" / "local" / "app.env").write_text("DD_PRINCIPAL_NAME=mine\n")
    assert common.ensure_local_tree() == []
    assert common.read_env(repo / "config" / "local" / "app.env") == {"DD_PRINCIPAL_NAME": "mine"}


def test_settings_files_of_the_old_layout_are_reported_with_where_they_move(repo: Path) -> None:
    (repo / ".env").write_text("DD_PRINCIPAL_NAME=x\n")
    (repo / "workbench" / "agents").mkdir(parents=True)
    (repo / "workbench" / "agents" / "orchestrator-model.env").write_text("ANTHROPIC_API_KEY=k\n")
    found = common.stray_files()
    assert any(f.startswith(".env -> config/local/app.env") for f in found)
    assert any(
        "workbench/agents/orchestrator-model.env -> config/local/agents/orchestrator-model.env" in f
        for f in found
    )


def test_the_agents_and_ports_come_from_the_apps_list() -> None:
    listed = ROOT / "app" / "config" / "agents.yaml"
    agents = common.load_agents(listed)
    entries = yaml.safe_load(listed.read_text(encoding="utf-8"))["agents"]
    assert [(a.name, a.url) for a in agents] == [(e["name"], e["url"].rstrip("/")) for e in entries]


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


def test_secret_set_stores_the_file_and_names_it_in_the_agents_own_settings(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    secret.dev_set("advisor-policy", "fairsharing-password", "pa55")
    stored = repo / "config" / "local" / "credentials" / "advisor-policy-fairsharing-password"
    assert stored.read_text() == "pa55\n"
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    own = common.read_env(repo / "config" / "local" / "agents" / "advisor-policy.env")
    assert own["FAIRSHARING_PASSWORD_FILE"] == stored.name
    secret.dev_list()
    assert "FAIRSHARING_PASSWORD_FILE" in capsys.readouterr().out

    secret.dev_remove("advisor-policy", "fairsharing-password")
    assert not stored.exists()
    own = common.read_env(repo / "config" / "local" / "agents" / "advisor-policy.env")
    assert "FAIRSHARING_PASSWORD_FILE" not in own


def test_secret_refuses_an_unknown_agent_or_a_bad_name(repo: Path) -> None:
    with pytest.raises(common.DevError, match="no agent"):
        secret.dev_set("advisor-nobody", "anthropic-api-key", "x")
    with pytest.raises(common.DevError, match="lower-case"):
        secret.dev_set("advisor-policy", "Bad_Name", "x")


def test_setup_and_start_are_refused_on_a_vm(capsys: pytest.CaptureFixture[str]) -> None:
    assert dd.main(["--target", "vm", "start"]) == 1
    assert "is for development" in capsys.readouterr().err

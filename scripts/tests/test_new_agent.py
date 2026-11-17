"""`dd.py new-agent`: the agent it writes passes every check without an edit (scripts/ddtool/new_agent.py).

The end-to-end tests write an agent into a copy of the repository, as the canaries in
test_architecture_canary.py do, and run the same checks CI runs over it: its own tests, mypy,
Import Linter, check_boundaries.py, check_members.py and check_deploy.py. They never touch the
working tree, and run what `uv run` would run with this interpreter, so need no network.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_boundaries as cb  # noqa: E402
import check_deploy as cd  # noqa: E402
import check_members as cm  # noqa: E402
from ddtool import new_agent as na  # noqa: E402
from ddtool.common import DevError  # noqa: E402

NAME = "advisor-generated"
NAMES = na.Names(NAME, port=8199)


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return [path for path in out.stdout.split("\0") if path and (ROOT / path).is_file()]


def _copy_repository(target: Path) -> Path:
    for path in _tracked():
        destination = target / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, destination)
    # check_boundaries.py reads the files git tracks.
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    subprocess.run(["git", "add", "."], cwd=target, check=True)
    return target


def _sources(root: Path) -> dict[str, str]:
    """An environment that imports every member from `root` ahead of the installed ones."""
    sources = [str(path.parent.parent) for path in sorted(root.glob("**/src/*/__init__.py"))]
    return {**os.environ, "PYTHONPATH": os.pathsep.join(sources)}


def _offline(command: list[str], cwd: Path) -> None:
    """What `uv run` would run, with this interpreter; `uv lock` needs the network, so not that."""
    if command[:2] == ["uv", "lock"]:
        return
    assert command[:2] == ["uv", "run"], command
    tool, *args = command[2:]
    program = {
        "dd-gen-schema": ["-c", "import sys; from dd_sdk.schema.gen import main; sys.exit(main())"],
        "ruff": ["-m", "ruff"],
    }[tool]
    subprocess.run([sys.executable, *program, *args], cwd=cwd, env=_sources(cwd), check=True)


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """A copy of the repository with NAME written into it by the generator."""
    root = _copy_repository(tmp_path_factory.mktemp("repository"))
    na.create(root, NAME, run=_offline)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    yield root


# --- Names and registration ---------------------------------------------------------------------


@pytest.mark.parametrize("name", ["advisor-foo", "example-two-words", "advisor-x2"])
def test_a_hyphenated_lower_case_name_is_accepted(name: str) -> None:
    na.check_name(name)


@pytest.mark.parametrize(
    "name", ["advisor", "Advisor-foo", "advisor_foo", "advisor-", "-foo", "a--b"]
)
def test_any_other_name_is_refused(name: str) -> None:
    with pytest.raises(DevError):
        na.check_name(name)


def test_every_name_comes_from_the_directory_name() -> None:
    assert NAMES.package == "dd_agent_advisor_generated"
    assert NAMES.distribution == "data-director-agent-advisor-generated"
    assert NAMES.script == "dd-advisor-generated"
    assert NAMES.agent_id == "advisor.generated"
    assert NAMES.agent_class == "AdvisorGenerated"


def test_the_port_is_one_past_the_highest_the_app_lists() -> None:
    ports = cd.listed_ports(ROOT / na.PORTS_FROM).values()
    assert na.next_port(ROOT) == max(port for port in ports if port is not None) + 1


def test_an_existing_agent_is_refused(generated: Path) -> None:
    with pytest.raises(DevError, match="already exists"):
        na.create(generated, NAME, run=_offline)


def test_it_is_listed_wherever_the_worked_example_is(generated: Path) -> None:
    port = f":{na.next_port(ROOT)}"
    for relative in (*na.YAML_FILES, "pyproject.toml", na.MKDOCS, na.ROSTER):
        text = (generated / relative).read_text(encoding="utf-8")
        # workbench/agents.yaml lists only URLs.
        assert any(name in text for name in (NAME, NAMES.agent_id, port)), relative
    assert (generated / na.ENV_DIR / f"{NAME}.env").is_file()
    roster = (generated / na.ROSTER).read_text(encoding="utf-8")
    assert f"`{NAMES.agent_id}`" in na.ROSTER_ROW.search(roster).group(2)  # type: ignore[union-attr]


def test_the_entries_name_its_own_script_and_port(generated: Path) -> None:
    compose = (generated / "compose.yaml").read_text(encoding="utf-8")
    port = na.next_port(ROOT)
    assert f"dd-{NAME} serve --host 0.0.0.0 --port {port}" in compose
    assert (
        (generated / na.ENV_DIR / f"{NAME}.env")
        .read_text(encoding="utf-8")
        .endswith(f"PORT={port}\n")
    )


# --- The checks CI runs --------------------------------------------------------------------------


def test_check_members_passes(generated: Path) -> None:
    assert cm.problems(generated) == []


def test_check_deploy_passes(generated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for constant in ("AGENTS", "ENV_DIR", "UNITS", "COMPOSE_AGENTS", "COMPOSE", "COMPOSE_IMAGE"):
        path: Path = getattr(cd, constant)
        monkeypatch.setattr(cd, constant, generated / path.relative_to(cd.ROOT))
    monkeypatch.setattr(cd, "ROOT", generated)
    assert cd.problems() == []


def test_check_boundaries_passes(generated: Path) -> None:
    assert cb.problems(generated) == []


def test_import_linter_passes(generated: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from importlinter.cli import lint_imports_command; lint_imports_command()",
            "--config",
            "pyproject.toml",
        ],
        cwd=generated,
        env=_sources(generated),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout


def test_mypy_passes(generated: Path) -> None:
    package = f"agents/{NAME}"
    result = subprocess.run(
        [sys.executable, "-m", "mypy", f"{package}/src", f"{package}/tests"],
        cwd=generated,
        env=_sources(generated),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout


def test_its_own_tests_pass(generated: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", f"agents/{NAME}", "-n0", "-p", "no:cacheprovider", "-q"],
        cwd=generated,
        env=_sources(generated),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout


def test_ruff_passes(generated: Path) -> None:
    for command in (["check"], ["format", "--check"]):
        result = subprocess.run(
            [sys.executable, "-m", "ruff", *command, f"agents/{NAME}"],
            cwd=generated,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout


# The tests outside the agent that read every in-tree agent.
ACROSS_AGENTS = (
    "scripts/tests/test_roster.py",
    "app/tests/test_app.py::test_the_reference_set_lists_and_enables_every_in_tree_agent",
    "workbench/tests/test_config.py::test_the_shipped_config_lists_every_agent_package",
)


def test_the_tests_across_every_agent_pass(generated: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *ACROSS_AGENTS, "-n0", "-p", "no:cacheprovider", "-q"],
        cwd=generated,
        env=_sources(generated),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout


def test_the_command_writes_into_the_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    import dd

    called: list[tuple[Path, str]] = []

    def record(root: Path, name: str) -> int:
        called.append((root, name))
        return 0

    monkeypatch.setattr(dd, "new_agent", record)
    assert dd.main(["--target", "dev", "new-agent", NAME]) == 0
    assert called == [(ROOT, NAME)]


def test_the_command_is_for_development(capsys: pytest.CaptureFixture[str]) -> None:
    import dd

    assert dd.main(["--target", "vm", "new-agent", NAME]) == 1
    assert "for development" in capsys.readouterr().err

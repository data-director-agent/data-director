"""scripts/agent_git_identity.sh sets only the author of an agent session's commits."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "agent_git_identity.sh"
PERSON = "Joe Heffer <60133133+Joe-Heffer-Shef@users.noreply.github.com>"


def run(env_file: Path, **env: str) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if not k.startswith(("DD_AUTHOR", "GIT_"))}
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env={**base, "CLAUDE_ENV_FILE": str(env_file), **env},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "env",
    [{}, {"DD_AUTHOR_NAME": "Joe Heffer"}, {"DD_AUTHOR_EMAIL": "joe@example.org"}],
)
def test_it_does_nothing_without_both_variables(tmp_path: Path, env: dict[str, str]) -> None:
    env_file = tmp_path / "env"
    assert run(env_file, **env).returncode == 0
    assert not env_file.exists()


def test_it_does_nothing_without_an_env_file() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env={"PATH": os.environ["PATH"], "DD_AUTHOR_NAME": "A", "DD_AUTHOR_EMAIL": "a@example.org"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


@pytest.mark.parametrize("bad", ["Joe\nHeffer", "Joe <Heffer>"])
def test_it_refuses_an_identity_that_would_corrupt_the_trailer(tmp_path: Path, bad: str) -> None:
    env_file = tmp_path / "env"
    result = run(env_file, DD_AUTHOR_NAME=bad, DD_AUTHOR_EMAIL="joe@example.org")
    assert result.returncode == 1
    assert not env_file.exists()


def test_the_author_is_the_person_and_the_committer_stays_the_agent(tmp_path: Path) -> None:
    env_file = tmp_path / "env"
    result = run(env_file, DD_AUTHOR_NAME="Joe Heffer", DD_AUTHOR_EMAIL=PERSON.split("<")[1][:-1])
    assert result.returncode == 0

    repo = tmp_path / "repo"
    repo.mkdir()
    base = {k: v for k, v in os.environ.items() if not k.startswith(("DD_AUTHOR", "GIT_"))}
    # Source the file the way the harness does, then commit as the agent would.
    script = (
        f". '{env_file}' && git init -q -b main && git config commit.gpgsign false"
        " && git config user.name Claude && git config user.email noreply@anthropic.com"
        " && git commit -q --allow-empty -m 'chore: x'"
        " && git log -1 --format='%an <%ae>|%cn <%ce>|%(trailers:key=Signed-off-by)'"
    )
    out = subprocess.run(
        ["bash", "-c", script], cwd=repo, env=base, capture_output=True, text=True, check=True
    ).stdout.strip()
    author, committer, trailers = out.split("|")
    assert author == PERSON
    assert committer == "Claude <noreply@anthropic.com>"
    assert trailers == ""  # no sign-off: only the person adds one

"""The sign-off rules in scripts/check_signoff.py: a human signs off, an agent only co-authors."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_signoff as cs  # noqa: E402

JOE = "Joe Heffer <joe@example.org>"
CLAUDE = "Claude <noreply@anthropic.com>"


def commit(author: str = JOE, *signoffs: str, subject: str = "fix(app): thing") -> cs.Commit:
    return cs.Commit("0123456789abcdef", author, subject, signoffs)


@pytest.mark.parametrize(
    "identity",
    [
        CLAUDE,
        "Claude Code <noreply@anthropic.com>",
        "Claude Opus 4.5 <noreply@anthropic.com>",
        "anthropic-bot <bot@anthropic.com>",
        "Copilot <175728472+Copilot@users.noreply.github.com>",
        "copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com>",
        "Codex <codex@openai.com>",
        "ChatGPT <chatgpt@openai.com>",
        "Gemini <gemini@google.com>",
        "devin-ai-integration[bot] <158243242+devin-ai-integration[bot]@users.noreply.github.com>",
        "Joe Heffer (aider) <joe@example.org>",
        "cursoragent <cursoragent@cursor.com>",
    ],
)
def test_agents_are_recognised(identity: str) -> None:
    assert cs.is_agent(identity)


@pytest.mark.parametrize(
    "identity",
    [
        JOE,
        "Devin Smith <devin@example.org>",
        "Cursor Jones <cj@example.org>",
        "dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
    ],
)
def test_people_and_dependabot_are_not_agents(identity: str) -> None:
    assert not cs.is_agent(identity)


def test_a_human_signing_their_own_commit_passes() -> None:
    assert cs.commit_problems(commit(JOE, JOE)) == []


def test_an_agent_may_co_author_a_commit_a_human_signs() -> None:
    # Co-authored-by is not read at all: only the Signed-off-by trailers are.
    assert cs.commit_problems(commit(JOE, JOE)) == []


def test_a_signoff_by_the_agent_is_rejected_even_beside_the_humans() -> None:
    problems = cs.commit_problems(commit(JOE, JOE, CLAUDE))
    assert len(problems) == 1
    assert "coding agent" in problems[0]


def test_a_signoff_by_the_agent_alone_is_rejected() -> None:
    problems = cs.commit_problems(commit(JOE, CLAUDE))
    assert any("signed off by a coding agent" in p for p in problems)
    assert any(f"no 'Signed-off-by: {JOE}'" in p for p in problems)


def test_a_commit_authored_and_signed_by_the_agent_is_rejected() -> None:
    problems = cs.commit_problems(commit(CLAUDE, CLAUDE))
    assert any("signed off by a coding agent" in p for p in problems)
    assert any("authored by a coding agent" in p for p in problems)


def test_a_commit_authored_by_the_agent_and_not_signed_is_rejected() -> None:
    problems = cs.commit_problems(commit(CLAUDE))
    assert len(problems) == 1
    assert "authored by a coding agent" in problems[0]


def test_a_human_author_with_an_agent_co_author_still_needs_the_humans_signoff() -> None:
    # What a session started with DD_AUTHOR_* commits: the person as author, no sign-off yet.
    person = "Joe Heffer <60133133+Joe-Heffer-Shef@users.noreply.github.com>"
    assert len(cs.commit_problems(commit(person))) == 1
    assert cs.commit_problems(commit(person, person)) == []


def test_the_signoff_must_match_the_author_byte_for_byte() -> None:
    person = "Joe Heffer <60133133+Joe-Heffer-Shef@users.noreply.github.com>"
    assert len(cs.commit_problems(commit(person, "Joe Heffer <j.heffer@sheffield.ac.uk>"))) == 1


def test_an_unsigned_human_commit_is_rejected() -> None:
    assert len(cs.commit_problems(commit(JOE))) == 1


def test_someone_elses_signoff_does_not_stand_in_for_the_authors() -> None:
    assert len(cs.commit_problems(commit(JOE, "Sam Other <sam@example.org>"))) == 1


def test_dependabot_is_exempt_from_signing_off() -> None:
    dependabot = "dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>"
    assert cs.commit_problems(commit(dependabot)) == []


def test_an_agent_bot_is_not_exempt_as_a_bot() -> None:
    bot = "copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com>"
    assert len(cs.commit_problems(commit(bot))) == 1


def test_an_agent_signoff_on_an_exempt_bot_commit_is_still_rejected() -> None:
    dependabot = "dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>"
    assert len(cs.commit_problems(commit(dependabot, CLAUDE))) == 1


def test_release_please_release_commits_are_exempt() -> None:
    release = commit("release-bot <r@example.org>", subject="chore(main): release 1.2.3")
    assert cs.commit_problems(release) == []


def test_parse_reads_trailers_from_git_log_output() -> None:
    log = (
        f"abc{cs.FIELD}{JOE}{cs.FIELD}fix: x{cs.FIELD}{JOE}\n{CLAUDE}\n{cs.RECORD}\n"
        f"def{cs.FIELD}{JOE}{cs.FIELD}fix: y{cs.FIELD}{cs.RECORD}"
    )
    first, second = cs.parse(log)
    assert first.signoffs == (JOE, CLAUDE)
    assert second.signoffs == ()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def test_main_against_a_real_repository(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.name", "Joe Heffer")
    _git(tmp_path, "config", "user.email", "joe@example.org")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: base")
    base = _git(tmp_path, "rev-parse", "HEAD")

    message = f"fix(app): good\n\nSigned-off-by: {JOE}\nCo-authored-by: {CLAUDE}\n"
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", message)
    good = _git(tmp_path, "rev-parse", "HEAD")

    message = f"fix(app): bad\n\nSigned-off-by: {JOE}\nSigned-off-by: {CLAUDE}\n"
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", message)
    bad = _git(tmp_path, "rev-parse", "HEAD")

    import os

    here = Path.cwd()
    os.chdir(tmp_path)
    try:
        assert cs.main([base, good]) == 0
        assert cs.main([base, bad]) == 1
    finally:
        os.chdir(here)
    assert "signed off by a coding agent" in capsys.readouterr().out

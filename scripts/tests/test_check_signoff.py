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
        "google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
        "copilot-swe-agent[bot]",
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
        "Claude Dupont <claude.dupont@example.fr>",
        "Jules Verne <jules@example.org>",
        "Ana Gemini <ana@example.org>",
        "dependabot[bot]",
        "dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
    ],
)
def test_people_and_dependabot_are_not_agents(identity: str) -> None:
    assert not cs.is_agent(identity)


def test_a_commit_without_a_signoff_passes() -> None:
    # The human sign-off is checked in the pull request description, not on each commit.
    assert cs.commit_problems(commit(JOE)) == []
    assert cs.commit_problems(commit(JOE, JOE)) == []


def test_an_agent_may_author_a_commit() -> None:
    assert cs.commit_problems(commit(CLAUDE)) == []


def test_a_signoff_by_the_agent_is_rejected_even_beside_the_humans() -> None:
    problems = cs.commit_problems(commit(JOE, JOE, CLAUDE))
    assert len(problems) == 1
    assert "coding agent" in problems[0]


def test_an_agent_signing_its_own_commit_is_rejected() -> None:
    assert len(cs.commit_problems(commit(CLAUDE, CLAUDE))) == 1


def test_an_agent_signoff_on_a_bot_commit_is_rejected() -> None:
    dependabot = "dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>"
    assert len(cs.commit_problems(commit(dependabot, CLAUDE))) == 1


BODY = "## Summary\n\nShow the history tab.\n\n---\n\nCo-authored-by: {CLAUDE}\n"


def body(*signoffs: str) -> str:
    lines = "".join(f"Signed-off-by: {s}\n" for s in signoffs)
    return BODY.format(CLAUDE=CLAUDE) + lines


def test_a_description_signed_off_by_a_human_passes() -> None:
    assert cs.description_problems(body(JOE)) == []


def test_a_description_from_the_browser_with_crlf_line_endings_passes() -> None:
    assert cs.description_problems(body(JOE).replace("\n", "\r\n")) == []


def test_a_description_without_a_signoff_is_rejected() -> None:
    problems = cs.description_problems(body())
    assert len(problems) == 1
    assert "no human" in problems[0]


def test_a_description_signed_off_only_by_the_agent_is_rejected() -> None:
    problems = cs.description_problems(body(CLAUDE))
    assert any("signed off by a coding agent" in p for p in problems)
    assert any("no human" in p for p in problems)


def test_an_agent_signoff_beside_the_humans_in_a_description_is_rejected() -> None:
    assert len(cs.description_problems(body(JOE, CLAUDE))) == 1


def test_a_signoff_without_an_address_does_not_count() -> None:
    assert len(cs.description_problems(body("Joe Heffer"))) == 1


def test_a_signoff_before_the_end_of_the_description_does_not_count() -> None:
    # git reads trailers only from the last paragraph, so this would not reach the merged commit.
    text = f"Signed-off-by: {JOE}\n\nMore text after it.\n"
    assert len(cs.description_problems(text)) == 1


def test_dependabot_pull_requests_need_no_signoff() -> None:
    assert cs.description_problems("Bumps a thing.", "build(deps): bump x", "dependabot[bot]") == []


def test_release_pull_requests_need_no_signoff() -> None:
    assert cs.description_problems("Release notes.", "chore(main): release 1.2.3", "joe") == []


def test_an_agent_bot_pull_request_is_not_exempt() -> None:
    assert len(cs.description_problems("Done.", "fix: x", "copilot-swe-agent[bot]")) == 1


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

    _git(tmp_path, "config", "user.name", "Claude")
    _git(tmp_path, "config", "user.email", "noreply@anthropic.com")
    message = f"fix(app): good\n\nCo-authored-by: {CLAUDE}\n"
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", message)
    good = _git(tmp_path, "rev-parse", "HEAD")

    message = f"fix(app): bad\n\nSigned-off-by: {JOE}\nSigned-off-by: {CLAUDE}\n"
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", message)
    bad = _git(tmp_path, "rev-parse", "HEAD")

    import os

    signed = tmp_path / "signed.md"
    signed.write_text(body(JOE), encoding="utf-8")
    unsigned = tmp_path / "unsigned.md"
    unsigned.write_text(body(), encoding="utf-8")

    here = Path.cwd()
    os.chdir(tmp_path)
    try:
        assert cs.main([base, good]) == 0
        assert cs.main([base, good, "--body-file", str(signed)]) == 0
        assert cs.main([base, good, "--body-file", str(unsigned)]) == 1
        assert cs.main([base, bad]) == 1
    finally:
        os.chdir(here)
    assert "signed off by a coding agent" in capsys.readouterr().out

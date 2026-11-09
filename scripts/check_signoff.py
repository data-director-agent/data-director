"""Check a pull request's Developer Certificate of Origin sign-off: a human gives it, never an agent.

A `Signed-off-by` trailer is a person's certification under the Developer Certificate of Origin
that they may submit the work. An agent cannot certify that: it may co-author work
(`Co-authored-by`) but never sign it off.

`main` is squash-merged, and its squash commit message is the pull request's title and
description, so the sign-off that lands on `main` is the one in the description. This reports

* a `Signed-off-by` trailer in any commit in `BASE..HEAD` (other than merges) that names a coding
  agent (see `AGENT`), whoever added it. Who authored a commit is not checked: an agent may;
* with `--body-file`, a `Signed-off-by` in the pull request description that names an agent, and
  a description with no human sign-off. Trailers are read by `git interpret-trailers`, as git
  reads them on the squash commit. A human signs off in one of two ways:

  - explicitly, with a `Signed-off-by: Name <email>` in the description's closing block of
    trailers, which becomes the merged commit's trailer; or
  - implicitly, by opening the pull request from their own GitHub account (`--author` a login
    that is neither a `[bot]` nor an agent). Under the organisation's contribution guide, opening
    a pull request certifies the Developer Certificate of Origin for it, so a pull request that a
    person opens with a coding agent's help (Claude Code on the web, say) passes without an edit.
    This is reported as a notice, not a problem.

  Dependabot's pull requests (`--author` a `[bot]` login that is not an agent) and
  release-please's release pull requests (`--title` starting `chore(main): release `) need no
  human sign-off. A pull request opened by an agent's own account needs an explicit one.

    python3 scripts/check_signoff.py BASE_SHA HEAD_SHA [--body-file F --title T --author LOGIN]

Without `--body-file` it checks the commits only, which is what to run locally before pushing.
It prints one line per problem, and one line starting `notice: ` per implicit sign-off, and exits
1 if there is any problem.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Coding agents, matched case-insensitively anywhere in a `Name <email>` identity or a GitHub
# login. Claude, Gemini, Jules, Devin and Cursor are also people's names, so these agents are
# matched by their addresses, bot logins or product names, never by a bare first name. Add an
# agent here as it appears.
AGENT = re.compile(
    r"anthropic|\bclaude[- ](?:code|opus|sonnet|haiku|fable)\b|"
    r"copilot|codex|openai|chatgpt|"
    r"gemini@google|gemini-code-assist|google-labs-jules|jules@google|"
    r"devin-ai|devin\.ai|cognition-ai|cursoragent|cursor agent|"
    r"\(aider\)|aider\.chat|"
    r"openhands|sweep-ai|amazon-q|codewhisperer|"
    r"\bcoding[- ]agent\b",
    re.IGNORECASE,
)

# Pull requests that need no human sign-off: Dependabot's, and release-please's release pull
# requests, which it opens with a personal access token. A bot that is also an agent
# (`copilot-swe-agent[bot]`) is not exempt.
BOT = re.compile(r"\[bot\]$")
RELEASE_SUBJECT = "chore(main): release "

# A sign-off names a person and their address.
IDENTITY = re.compile(r"^[^<>]*\S[^<>]*<[^<>@\s]+@[^<>\s]+>$")

SIGNED_OFF_BY = "signed-off-by"

FIELD = "\x1f"
RECORD = "\x1e"
# sha, author, subject, then the Signed-off-by trailer values, one per line.
FORMAT = f"%H{FIELD}%an <%ae>{FIELD}%s{FIELD}%(trailers:key=Signed-off-by,valueonly,unfold){RECORD}"

NOTICE = "notice: "

HOW = (
    "The person who takes responsibility for the pull request adds 'Signed-off-by: Name <email>'"
    " as the last line of its description, which becomes the merged commit's trailer, or opens"
    " the pull request from their own GitHub account. Never let an agent sign off."
)


@dataclass(frozen=True)
class Commit:
    sha: str
    author: str  # "Name <email>"
    subject: str
    signoffs: tuple[str, ...]  # the values of its Signed-off-by trailers


def is_agent(identity: str) -> bool:
    """Whether `identity` ("Name <email>", or a login) names a coding agent."""
    return AGENT.search(identity) is not None


def agent_signoff(where: str, signoff: str) -> str:
    return (
        f"{where}: signed off by a coding agent ('Signed-off-by: {signoff}'); only a human can"
        " sign off, an agent may co-author"
    )


def commit_problems(commit: Commit) -> list[str]:
    """What is wrong with the sign-offs of `commit`; empty if nothing."""
    label = f"{commit.sha[:7]} {commit.subject}"
    return [agent_signoff(label, signoff) for signoff in commit.signoffs if is_agent(signoff)]


def trailers(message: str) -> list[tuple[str, str]]:
    """The (key, value) trailers git reads at the end of `message`."""
    out = subprocess.run(
        ["git", "interpret-trailers", "--parse", "--no-divider"],
        input=message.replace("\r\n", "\n"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    pairs = []
    for line in out.splitlines():
        key, _, value = line.partition(":")
        pairs.append((key.strip(), value.strip()))
    return pairs


def is_exempt(title: str, author: str) -> bool:
    """Whether a pull request needs no human sign-off (Dependabot, release-please)."""
    if title.startswith(RELEASE_SUBJECT):
        return True
    return BOT.search(author) is not None and not is_agent(author)


def is_person(login: str) -> bool:
    """Whether a GitHub `login` is a person's account: not empty, not a bot, not an agent."""
    return bool(login) and BOT.search(login) is None and not is_agent(login)


def human_signoffs(body: str) -> list[str]:
    """The human `Signed-off-by` values in the closing trailers of a pull request description."""
    signoffs = [value for key, value in trailers(body) if key.lower() == SIGNED_OFF_BY]
    return [s for s in signoffs if not is_agent(s) and IDENTITY.match(s)]


def description_problems(body: str, title: str = "", author: str = "") -> list[str]:
    """What is wrong with the sign-off in a pull request description; empty if nothing.

    A description with no human `Signed-off-by` passes when `author`, who opened the pull
    request, is a person: opening it is their implicit sign-off (see `implicit_signoff`).
    """
    signoffs = [value for key, value in trailers(body) if key.lower() == SIGNED_OFF_BY]
    problems = [
        agent_signoff("pull request description", signoff)
        for signoff in signoffs
        if is_agent(signoff)
    ]
    if not human_signoffs(body) and not is_exempt(title, author) and not is_person(author):
        problems.append(
            "pull request description: no human 'Signed-off-by: Name <email>' in the trailers"
            " at its end, and the pull request was not opened by a person's account"
        )
    return problems


def implicit_signoff(body: str, title: str = "", author: str = "") -> str | None:
    """The notice for a pull request a person signs off by opening it; None if not that case."""
    if human_signoffs(body) or is_exempt(title, author) or not is_person(author):
        return None
    return (
        f"{NOTICE}pull request description: no explicit 'Signed-off-by'; @{author} certifies the"
        " Developer Certificate of Origin by opening the pull request"
    )


def parse(log: str) -> list[Commit]:
    """The commits in the output of `git log --format=FORMAT`."""
    commits = []
    for record in log.split(RECORD):
        if not record.strip():
            continue
        sha, author, subject, trailer_values = record.strip("\n").split(FIELD)
        signoffs = tuple(line.strip() for line in trailer_values.splitlines() if line.strip())
        commits.append(Commit(sha.strip(), author, subject, signoffs))
    return commits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base")
    parser.add_argument("head")
    parser.add_argument("--body-file", type=Path, help="the pull request description")
    parser.add_argument("--title", default="", help="the pull request title")
    parser.add_argument("--author", default="", help="the pull request author's login")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    log = subprocess.run(
        ["git", "log", "--no-merges", f"--format={FORMAT}", f"{args.base}..{args.head}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    problems = [problem for commit in parse(log) for problem in commit_problems(commit)]
    if args.body_file is not None:
        body = args.body_file.read_text(encoding="utf-8")
        problems += description_problems(body, args.title, args.author)
        notice = implicit_signoff(body, args.title, args.author)
        if notice is not None:
            print(notice)
    for problem in problems:
        print(problem)
    if problems:
        print(HOW, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

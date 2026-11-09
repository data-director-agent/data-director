"""Check that every commit in a pull request is signed off by a human, never by a coding agent.

A `Signed-off-by` trailer is a person's certification under the Developer Certificate of Origin
that they may submit the work. An agent cannot certify that, so only a human can approve a commit:
the agent may co-author it (`Co-authored-by`) but not sign it off. For each commit in
`BASE..HEAD`, other than merges, this reports

* a `Signed-off-by` trailer that names a coding agent (see `AGENT`), whoever added it;
* a commit with no `Signed-off-by` trailer naming its author, unless the author is a known
  dependency bot (Dependabot) or the commit is release-please's release commit.

A commit that an agent authored therefore fails twice over: it is signed off by the agent, or not
signed off at all. The human who takes responsibility for it signs it off and, if they did not
make it, rewrites the author with `git rebase --signoff` and `git commit --amend --reset-author`.

    python3 scripts/check_signoff.py BASE_SHA HEAD_SHA

It prints one line per problem and exits 1 if there is any.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass

# Names and addresses of coding agents. Matched, case-insensitively, anywhere in a `Name <email>`
# identity. Kept to names that are not people's: "Devin" and "Cursor" alone would catch humans, so
# those are matched by their products' addresses and bot names. Add an agent here as it appears.
AGENT = re.compile(
    r"claude|anthropic|copilot|codex|openai|chatgpt|gemini|jules|"
    r"devin-ai|devin\.ai|cognition-ai|cursoragent|cursor agent|"
    r"\(aider\)|aider\.chat|"
    r"openhands|sweep-ai|amazon-q|codewhisperer|"
    r"\bcoding[- ]agent\b",
    re.IGNORECASE,
)

# Bots whose commits carry no human sign-off: Dependabot signs off with an address other than the
# one it commits from, and release-please makes release commits with a personal access token.
# A bot that is also an agent (`copilot-swe-agent[bot]`) is not exempt.
BOT = re.compile(r"\[bot\] <")
RELEASE_SUBJECT = "chore(main): release "

FIELD = "\x1f"
RECORD = "\x1e"
# sha, author, subject, then the Signed-off-by trailer values, one per line.
FORMAT = f"%H{FIELD}%an <%ae>{FIELD}%s{FIELD}%(trailers:key=Signed-off-by,valueonly,unfold){RECORD}"


@dataclass(frozen=True)
class Commit:
    sha: str
    author: str  # "Name <email>"
    subject: str
    signoffs: tuple[str, ...]  # the values of its Signed-off-by trailers


def is_agent(identity: str) -> bool:
    """Whether `identity` ("Name <email>") names a coding agent."""
    return AGENT.search(identity) is not None


def commit_problems(commit: Commit) -> list[str]:
    """What is wrong with the sign-off of `commit`; empty if nothing."""
    label = f"{commit.sha[:7]} {commit.subject}"
    problems = [
        f"{label}: signed off by a coding agent ('Signed-off-by: {signoff}'); only a human can"
        " sign off a commit, an agent may co-author it"
        for signoff in commit.signoffs
        if is_agent(signoff)
    ]
    if BOT.search(commit.author) and not is_agent(commit.author):
        return problems
    if commit.subject.startswith(RELEASE_SUBJECT):
        return problems
    if is_agent(commit.author):
        problems.append(
            f"{label}: authored by a coding agent ({commit.author}); a human must take the"
            " commit over as its author and sign it off"
        )
    elif commit.author not in commit.signoffs:
        problems.append(f"{label}: no 'Signed-off-by: {commit.author}'")
    return problems


def parse(log: str) -> list[Commit]:
    """The commits in the output of `git log --format=FORMAT`."""
    commits = []
    for record in log.split(RECORD):
        if not record.strip():
            continue
        sha, author, subject, trailers = record.strip("\n").split(FIELD)
        signoffs = tuple(line.strip() for line in trailers.splitlines() if line.strip())
        commits.append(Commit(sha.strip(), author, subject, signoffs))
    return commits


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        print("usage: check_signoff.py BASE_SHA HEAD_SHA", file=sys.stderr)
        return 2
    base, head = args
    log = subprocess.run(
        ["git", "log", "--no-merges", f"--format={FORMAT}", f"{base}..{head}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    problems = [problem for commit in parse(log) for problem in commit_problems(commit)]
    for problem in problems:
        print(problem)
    if problems:
        print(
            "A person signs off with 'git commit -s'; amend earlier commits with"
            f" 'git rebase --signoff {base}'. Never let an agent do it.",
            file=sys.stderr,
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

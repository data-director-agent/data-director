"""Check a pull request's title and branch name against the repository's naming rules.

A pull request is squash-merged, so its title becomes the commit subject on main, and
release-please reads that subject as a Conventional Commit to decide each package's next version
and changelog entry. The title therefore takes the form

    type(scope)!: summary

where `type` is one of `TYPES`, `(scope)` and `!` (a breaking change) are optional, and the
summary is lower case, has no closing full stop and fits in `MAX_TITLE` characters. A branch name
is lower-case words joined by hyphens, optionally grouped with slashes (`ci-faster`,
`harness/run-store`), in at most `MAX_BRANCH` characters.

    uv run python scripts/check_names.py --title "feat(app): history tab" --branch app-history

Either option may be left out. Pull requests from Dependabot's and release-please's branches are
exempt: their titles and branch names are fixed by the tool. It prints one line per problem and
exits 1 if there is any.
"""

from __future__ import annotations

import argparse
import re
import sys

# The Conventional Commits types this repository uses (the Angular set). release-please makes a
# release for `feat` and `fix`, and for any type with `!`.
TYPES = (
    "build",
    "chore",
    "ci",
    "docs",
    "feat",
    "fix",
    "perf",
    "refactor",
    "revert",
    "style",
    "test",
)

# Long enough for the longest Conventional Commit subject already on main (86 characters), short
# enough that the subject, with the " (#NNN)" GitHub appends on merge, reads in one log line.
MAX_TITLE = 90

# Long enough for a few descriptive words; branch names appear in worktree paths and CI logs.
MAX_BRANCH = 60

# Branches whose pull requests follow their own tool's naming, which this repository cannot change.
# release-please opens its pull requests with a personal access token, so the author is no guide.
EXEMPT_BRANCHES = ("dependabot/", "release-please--")

TITLE = re.compile(r"(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<breaking>!)?: (?P<summary>.*)")
SCOPE = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")
BRANCH = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*")
# A capitalised ordinary word ("Add", "Fix"); acronyms and names such as "CI" or "GitHub" pass.
CAPITALISED = re.compile(r"[A-Z][a-z]+")


def title_problems(title: str) -> list[str]:
    """What is wrong with pull request title `title`; empty if nothing."""
    m = TITLE.fullmatch(title)
    if m is None:
        return [f"title {title!r} is not 'type(scope): summary' (Conventional Commits)"]
    problems = []
    if m["type"] not in TYPES:
        problems.append(f"type {m['type']!r} is not one of {', '.join(TYPES)}")
    scope = m["scope"]
    if scope is not None and SCOPE.fullmatch(scope) is None:
        problems.append(f"scope {scope!r} is not lower-case words joined by hyphens")
    summary = m["summary"]
    if not summary.strip():
        problems.append("the summary after ': ' is empty")
    else:
        if summary != summary.strip():
            problems.append("the summary starts or ends with white space")
        if CAPITALISED.fullmatch(summary.split()[0]):
            problems.append(f"the summary starts with a capital ({summary.split()[0]!r})")
        if summary.endswith("."):
            problems.append("the summary ends with a full stop")
    if len(title) > MAX_TITLE:
        problems.append(f"title is {len(title)} characters; the limit is {MAX_TITLE}")
    return problems


def branch_problems(branch: str) -> list[str]:
    """What is wrong with branch name `branch`; empty if nothing."""
    problems = []
    if BRANCH.fullmatch(branch) is None:
        problems.append(
            f"branch {branch!r} is not lower-case words joined by hyphens"
            " (with optional '/' groups), e.g. 'ci-faster'"
        )
    if len(branch) > MAX_BRANCH:
        problems.append(f"branch is {len(branch)} characters; the limit is {MAX_BRANCH}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--title", help="the pull request title")
    parser.add_argument("--branch", help="the pull request's head branch")
    args = parser.parse_args(argv)
    if args.branch is not None and args.branch.startswith(EXEMPT_BRANCHES):
        return 0
    problems = []
    if args.title is not None:
        problems += title_problems(args.title)
    if args.branch is not None:
        problems += branch_problems(args.branch)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

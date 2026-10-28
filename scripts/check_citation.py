# /// script
# requires-python = ">=3.14"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Check that everyone who has written a commit is an author in CITATION.cff.

Each person who authors or co-authors a commit (a `Co-authored-by:` trailer) is cited as an author
of the software (CONTRIBUTING.md, "Credit"). Git knows only a name and an email address, not
the ORCID and affiliation a citation needs, so this script does not write the file: it reports
who is missing, and the contributor adds their own entry.

    uv run scripts/check_citation.py

It reads the full history of `HEAD`, so CI checks it out with `fetch-depth: 0`. Each identity is
first resolved through `.mailmap`, which gathers one person's addresses under one name and
address. A person is listed when that address is an author's `email`, or that name is an
author's `given-names` and `family-names` or `name`. Bots and AI assistants are not authors and
are skipped. It prints one `Name <email>` per missing person and exits 1 if there is any.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CITATION = ROOT / "CITATION.cff"

# Identities that write commits without being authors: GitHub's bot accounts (Dependabot,
# github-actions) and the AI assistants named in `Co-authored-by:` trailers.
NOT_AUTHOR_SUFFIXES = ("[bot]@users.noreply.github.com", "@anthropic.com")

# One record per commit: the author, then each co-author on its own line.
LOG_FORMAT = "%aN <%aE>%n%(trailers:key=Co-authored-by,valueonly,unfold)%x00"


def run_git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, check=True, text=True
    ).stdout


def contributors() -> set[str]:
    """Every `Name <email>` that authors or co-authors a commit, after `.mailmap`."""
    raw = {
        line.strip()
        for line in run_git("log", f"--format={LOG_FORMAT}", "HEAD").splitlines()
        if "<" in line
    }
    # Trailers are not mapped by `git log`; `check-mailmap` maps author and co-author alike.
    mapped = run_git("check-mailmap", *sorted(raw)).splitlines() if raw else []
    return {identity for identity in mapped if not is_bot(identity)}


def is_bot(identity: str) -> bool:
    return email_of(identity).endswith(NOT_AUTHOR_SUFFIXES)


def name_of(identity: str) -> str:
    return identity.partition("<")[0].strip()


def email_of(identity: str) -> str:
    return identity.partition("<")[2].rstrip(">").strip().lower()


def cited(authors: list[dict[str, str]]) -> tuple[set[str], set[str]]:
    """The names and the email addresses of the authors in a CITATION.cff."""
    names, emails = set(), set()
    for author in authors:
        if "name" in author:
            names.add(author["name"].casefold())
        given, family = author.get("given-names", ""), author.get("family-names", "")
        if given or family:
            names.add(f"{given} {family}".strip().casefold())
        if "email" in author:
            emails.add(author["email"].lower())
    return names, emails


def missing(people: set[str], authors: list[dict[str, str]]) -> list[str]:
    """Each of `people` who is not one of `authors`, sorted."""
    names, emails = cited(authors)
    return sorted(
        person
        for person in people
        if email_of(person) not in emails and name_of(person).casefold() not in names
    )


def main() -> int:
    if run_git("rev-parse", "--is-shallow-repository").strip() == "true":
        print("a shallow clone has only part of the history; fetch it all", file=sys.stderr)
        return 2
    authors = yaml.safe_load(CITATION.read_text(encoding="utf-8"))["authors"]
    absent = missing(contributors(), authors)
    for person in absent:
        print(person)
    if absent:
        print(
            f"{len(absent)} contributor(s) not in CITATION.cff; add yourself to `authors` "
            "(CONTRIBUTING.md, Credit)",
            file=sys.stderr,
        )
    return 1 if absent else 0


if __name__ == "__main__":
    sys.exit(main())

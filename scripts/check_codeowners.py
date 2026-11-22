"""Check that .github/CODEOWNERS covers the repository and has no dead rule.

GitHub does not report a changed path that no rule owns, and it uses the last matching line, so a
rule written after a broader one can hide it. This checks that every file git tracks has an owner
and that every rule matches at least one tracked file.

    uv run --no-project python scripts/check_codeowners.py

It prints one problem per line and exits 1 if there is any. Patterns follow gitignore rules as
CODEOWNERS uses them: a leading `/` anchors at the root, a pattern with no other `/` matches at any
depth, a trailing `/` names a directory, `*` stays within one name and `**` crosses directories.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODEOWNERS = ".github/CODEOWNERS"


def pattern_regex(pattern: str) -> re.Pattern[str]:
    """The regular expression for a CODEOWNERS `pattern`, matched against a repository path."""
    directory = pattern.endswith("/")
    body = pattern.strip("/")
    anchored = pattern.startswith("/") or "/" in body
    out = []
    i = 0
    while i < len(body):
        if body.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif body.startswith("**", i):
            out.append(".*")
            i += 2
        elif body[i] == "*":
            out.append("[^/]*")
            i += 1
        elif body[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(body[i]))
            i += 1
    prefix = "" if anchored else "(?:.*/)?"
    # A name matches the file or directory itself and, for a directory, everything beneath it.
    tail = "/.*" if directory else "(?:/.*)?"
    return re.compile(f"^{prefix}{''.join(out)}{tail}$")


def parse(text: str) -> list[tuple[int, str, list[str]]]:
    """`(line number, pattern, owners)` for each rule; an empty owner list unsets ownership."""
    rules = []
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.split(" #")[0].strip()
        if line and not line.startswith("#"):
            pattern, *owners = line.split()
            rules.append((number, pattern, owners))
    return rules


def problems(text: str, paths: list[str]) -> list[str]:
    rules = [(n, p, o, pattern_regex(p)) for n, p, o in parse(text)]
    owned: dict[str, list[str]] = {path: [] for path in paths}
    used = set()
    for number, _, owners, regex in rules:
        for path in paths:
            if regex.match(path):
                owned[path] = owners
                used.add(number)
    found = [
        f"{CODEOWNERS}:{number}: `{pattern}` matches no tracked file"
        for number, pattern, _, _ in rules
        if number not in used
    ]
    found += [f"{path}: no owner" for path, owners in owned.items() if not owners]
    return found


def main() -> int:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True, text=True
    )
    paths = [p for p in out.stdout.split("\0") if p]
    found = problems((ROOT / CODEOWNERS).read_text(encoding="utf-8"), paths)
    for problem in found:
        print(problem)
    if found:
        print(f"{len(found)} problem(s) in {CODEOWNERS}", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())

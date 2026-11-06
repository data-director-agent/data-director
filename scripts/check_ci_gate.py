#!/usr/bin/env python3
"""Check that each aggregate job in a workflow waits for every other job in it.

"CI passed" and "Accessibility passed" are the checks the branch ruleset requires and that
deploy/deploy.sh reads. A job added to the workflow but not to the aggregate's `needs` runs, but
nothing depends on it, so it can fail and the commit still deploys. This reads the workflow text
with the standard library only, so that it runs in the `workflows` job without installing the
workspace.

    scripts/check_ci_gate.py [--root DIR]

Exits 1, naming each missing job, when a gate leaves one out.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# workflow file -> (aggregate job id, jobs the aggregate deliberately leaves out).
GATES: dict[str, tuple[str, frozenset[str]]] = {
    # `conformance` is advisory (TODO(#458)): it reports and never blocks a merge.
    ".github/workflows/ci.yml": ("ci-passed", frozenset({"conformance"})),
    ".github/workflows/accessibility.yml": ("accessibility-passed", frozenset()),
}

JOB = re.compile(r"^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$")
ITEM = re.compile(r"^      - ([A-Za-z0-9_-]+)\s*(?:#.*)?$")


def jobs_and_needs(text: str, gate: str) -> tuple[list[str], set[str]]:
    """Return every job id under `jobs:` and the gate's `needs` list."""
    in_jobs = False
    current = ""
    in_needs = False
    jobs: list[str] = []
    needs: set[str] = set()
    for line in text.splitlines():
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if re.match(r"^\S", line):  # another top-level key ends the jobs
            break
        match = JOB.match(line)
        if match:
            current = match.group(1)
            jobs.append(current)
            in_needs = False
            continue
        if current != gate:
            continue
        if inline := re.match(r"^    needs:\s*\[(.*)\]\s*(?:#.*)?$", line):
            needs.update(name.strip() for name in inline.group(1).split(",") if name.strip())
        elif re.match(r"^    needs:\s*$", line):
            in_needs = True
        elif in_needs and (item := ITEM.match(line)):
            needs.add(item.group(1))
        elif re.match(r"^    \S", line):
            in_needs = False
    return jobs, needs


def check(root: Path) -> list[str]:
    problems: list[str] = []
    for path, (gate, exempt) in GATES.items():
        file = root / path
        if not file.is_file():
            problems.append(f"{path}: not found")
            continue
        jobs, needs = jobs_and_needs(file.read_text(encoding="utf-8"), gate)
        if gate not in jobs:
            problems.append(f"{path}: no job '{gate}'")
            continue
        if not needs:
            problems.append(f"{path}: '{gate}' has no `needs` list")
            continue
        problems.extend(
            f"{path}: job '{job}' is not in the `needs` of '{gate}', so its failure would not "
            f"fail the gate (add it, or list it in GATES here with the reason)"
            for job in jobs
            if job != gate and job not in needs and job not in exempt
        )
        problems.extend(
            f"{path}: '{gate}' needs '{job}', which is not a job in the workflow"
            for job in sorted(needs - set(jobs))
        )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    problems = check(parser.parse_args().root)
    for problem in problems:
        print(f"::error::{problem}" if "GITHUB_ACTIONS" in os.environ else problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

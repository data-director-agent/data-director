"""Render CONFORMANCE.md from the requirements register, the review record and a test run.

Each requirement is assessed in one or two lanes, named by its `assessed_by` entry in the
register (ADR-0014). Each lane gives a verdict, and the lanes are never combined into one.

The test lane applies the traceability rule. A requirement is

- **substantiated**  if at least one test marked with its identifier passed and none failed;
- **contradicted**   if any test marked with its identifier failed;
- **unsubstantiated** otherwise — no marked test, or only skipped tests.

The review lane reads the latest review of the requirement in docs/reviews.yaml. It is

- **substantiated**  if that review found the requirement met;
- **contradicted**   if that review found it not met;
- **unsubstantiated** if no review has been recorded.

A report in which most rows are honestly unsubstantiated is the intended first governance
artefact. "Substantiated by an example-based test" is not a conformance claim; the footer says so.

Usage, from the repository root (one test session covers the whole workspace):
    uv run pytest --json-report --json-report-file=workbench/.report.json
    uv run python workbench/scripts/conformance_report.py            # writes CONFORMANCE.md
    uv run python workbench/scripts/conformance_report.py --check    # exit 1 if the table changes
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "docs" / "requirements.yaml"
REVIEWS = ROOT / "docs" / "reviews.yaml"
REPORT = ROOT / ".report.json"
OUTPUT = ROOT / "CONFORMANCE.md"

SUBSTANTIATED = "substantiated"
CONTRADICTED = "contradicted"
UNSUBSTANTIATED = "unsubstantiated"
MARKERS = {SUBSTANTIATED: "✅", CONTRADICTED: "❌", UNSUBSTANTIATED: "⬜"}

TEST = "test"
REVIEW = "review"
LANES = (TEST, REVIEW)
DEFAULT_LANES = [TEST]

# A review's finding, and the verdict it gives the review lane.
REVIEW_VERDICTS = {"meets": SUBSTANTIATED, "does-not-meet": CONTRADICTED}
REVIEW_FIELDS = ("requirement", "verdict", "reviewer", "date", "commit", "scope", "record")
COMMIT = re.compile(r"^[0-9a-f]{7,40}$")

TABLE_START = "<!-- conformance-table:start -->"
TABLE_END = "<!-- conformance-table:end -->"


class RegisterError(ValueError):
    """The register or the review record is malformed. A configuration error, not a verdict."""


def lanes(req: dict[str, Any]) -> list[str]:
    """The lanes a requirement is assessed in; `test` alone when the register names none."""
    named: list[str] = req.get("assessed_by", DEFAULT_LANES)
    unknown = [lane for lane in named if lane not in LANES]
    if not named or unknown:
        raise RegisterError(f"{req['id']}: assessed_by must name one or more of {list(LANES)}")
    return named


def load_register(path: Path = REGISTER) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    reqs: list[dict[str, Any]] = data["requirements"]
    for req in reqs:
        lanes(req)
    return reqs


def load_reviews(register: list[dict[str, Any]], path: Path = REVIEWS) -> list[dict[str, Any]]:
    """Read and check the review record. Every problem is raised, never skipped."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    reviews: list[dict[str, Any]] = data.get("reviews") or []
    reviewable = {r["id"] for r in register if REVIEW in lanes(r)}
    for n, review in enumerate(reviews, start=1):
        where = f"{path.name} entry {n}"
        missing = [f for f in REVIEW_FIELDS if not review.get(f)]
        if missing:
            raise RegisterError(f"{where}: missing {missing}")
        if review["requirement"] not in reviewable:
            raise RegisterError(
                f"{where}: {review['requirement']} is not a registered requirement assessed by review"
            )
        if review["verdict"] not in REVIEW_VERDICTS:
            raise RegisterError(f"{where}: verdict must be one of {list(REVIEW_VERDICTS)}")
        if not isinstance(review["date"], dt.date):
            raise RegisterError(f"{where}: date must be an unquoted YYYY-MM-DD date")
        if not COMMIT.match(str(review["commit"])):
            raise RegisterError(f"{where}: commit must be a hexadecimal git commit hash")
    return reviews


def load_report(path: Path = REPORT) -> dict[str, Any]:
    if not path.is_file():
        sys.exit(
            f"{path} not found; run `uv run pytest --json-report --json-report-file={path}` first"
        )
    report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return report


def tests_by_requirement(report: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    """requirement id -> [(nodeid, outcome)], read from the metadata the conftest hook wrote."""
    index: dict[str, list[tuple[str, str]]] = {}
    for test in report.get("tests", []):
        ids = (test.get("metadata") or {}).get("requirements") or []
        for rid in ids:
            index.setdefault(rid, []).append((test["nodeid"], test["outcome"]))
    return index


def verdict(tests: list[tuple[str, str]]) -> str:
    outcomes = {o for _, o in tests}
    if "failed" in outcomes or "error" in outcomes:
        return CONTRADICTED
    if "passed" in outcomes:
        return SUBSTANTIATED
    return UNSUBSTANTIATED


def latest_reviews(reviews: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """requirement id -> its latest review. On the same date, the later entry in the file wins."""
    latest: dict[str, dict[str, Any]] = {}
    for review in reviews:
        held = latest.get(review["requirement"])
        if held is None or review["date"] >= held["date"]:
            latest[review["requirement"]] = review
    return latest


def review_verdict(review: dict[str, Any] | None) -> str:
    return UNSUBSTANTIATED if review is None else REVIEW_VERDICTS[review["verdict"]]


def _short(nodeid: str) -> str:
    return nodeid.split("::")[-1]


def _cell(v: str) -> str:
    return f"{MARKERS[v]} **{v}**"


def render_table(
    register: list[dict[str, Any]],
    index: dict[str, list[tuple[str, str]]],
    latest: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, dict[str, int]]]:
    rows = [
        "| ID | Source | Title | Test verdict | Tests | Review verdict | Review |",
        "|---|---|---|---|---|---|---|",
    ]
    counts = {lane: dict.fromkeys(MARKERS, 0) for lane in LANES}
    for req in register:
        named = lanes(req)
        parent = f" (under {req['parent']})" if req.get("parent") else ""
        cells = [req["id"], f"{req['source']}{parent}", req["title"]]
        if TEST in named:
            tests = index.get(req["id"], [])
            v = verdict(tests)
            counts[TEST][v] += 1
            names = ", ".join(
                f"`{_short(n)}`" + ("" if o == "passed" else f" ({o})") for n, o in sorted(tests)
            )
            cells += [_cell(v), names or "—"]
        else:
            cells += ["not assessed", "—"]
        if REVIEW in named:
            review = latest.get(req["id"])
            v = review_verdict(review)
            counts[REVIEW][v] += 1
            detail = (
                "—"
                if review is None
                else f"{review['reviewer']}, {review['date'].isoformat()}, "
                f"`{str(review['commit'])[:7]}`, [record]({review['record']})"
            )
            cells += [_cell(v), detail]
        else:
            cells += ["not assessed", "—"]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows), counts


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        ).stdout.strip()
    except OSError, subprocess.CalledProcessError:
        return "unknown"


def render(
    register: list[dict[str, Any]],
    report: dict[str, Any],
    reviews: list[dict[str, Any]] | None = None,
) -> str:
    index = tests_by_requirement(report)
    unregistered = sorted(set(index) - {r["id"] for r in register})
    untestable = sorted(r["id"] for r in register if r["id"] in index and TEST not in lanes(r))
    table, counts = render_table(register, index, latest_reviews(reviews or []))
    summary = report.get("summary", {})
    created = datetime.fromtimestamp(report.get("created", 0), tz=UTC).isoformat(timespec="seconds")
    summary_rows = "\n".join(f"| {v} | {counts[TEST][v]} | {counts[REVIEW][v]} |" for v in MARKERS)
    head = f"""# Conformance report

**Generated:** {created} · **Commit:** `{git_commit()}` · **Python:** {platform.python_version()} · **Test run:** {summary.get("passed", 0)} passed, {summary.get("failed", 0)} failed, {summary.get("skipped", 0)} skipped of {summary.get("total", 0)}

This file is generated by `scripts/conformance_report.py` from `docs/requirements.yaml`,
`docs/reviews.yaml` and a `pytest-json-report` run. Do not edit it by hand. How the report works
is described in `docs/conformance.md`.

## How to read it

Each row is a requirement in the register. The register says how each requirement is assessed:
by automated test, by human review, or by both (ADR-0014). Each assessment gives its own verdict,
and the two are never combined into one. A requirement not assessed one way reads *not assessed*
in that column.

The **test verdict** applies the traceability rule:

- **substantiated** — at least one test marked `@pytest.mark.requirement("<ID>")` passed in this run and none failed;
- **contradicted** — a test marked with the identifier failed;
- **unsubstantiated** — no test claims the identifier, or every claiming test was skipped.

The **review verdict** reads the latest review recorded for the requirement in `docs/reviews.yaml`:

- **substantiated** — the reviewer found the requirement met at the commit named;
- **contradicted** — the reviewer found it not met;
- **unsubstantiated** — no review has been recorded.

*Substantiated* by a test means an example-based test exercised one path through the
requirement. *Substantiated* by a review means one named person examined the scope described in
the review record at one commit. Either way it is **not** a conformance claim, an evaluation
result, or evidence that the requirement is met in general. Rows marked unsubstantiated are the honest
default and the point of publishing this file: the Blueprint's Appendix D records implementers'
stated intentions; this table records what a test run and the recorded reviews actually showed.

`source: blueprint` rows use the Blueprint's own identifiers and titles (§7). `source: project`
rows are identifiers this project introduced (the R3.n decomposition from
`experiments/standards-advisor`, and `DD-*` for the contract itself); the Blueprint does not use
them.

## Summary

| Verdict | By test | By review |
|---|---|---|
{summary_rows}

"""
    body = f"{TABLE_START}\n{table}\n{TABLE_END}\n"
    if unregistered:
        body += f"\n> ⚠️ Tests claimed identifiers not in the register: {', '.join(unregistered)}. Register them or remove the markers.\n"
    if untestable:
        body += f"\n> ⚠️ Tests claimed identifiers the register assesses by review only: {', '.join(untestable)}. Add `test` to their `assessed_by` or remove the markers.\n"
    foot = """
## Attestation

This report is not signed. The intent is to attest it with in-toto or Sigstore once the project
has a release process; until then, the commit hash above and the CI job that regenerates this file
are the only link between the table and the code (see docs/adr/0006-dependency-tiering.md,
"Rejected for v0"). A review is attested only by its entry in `docs/reviews.yaml` and the commit
that added it.

## Regenerating

```sh
uv run pytest --json-report --json-report-file=workbench/.report.json
uv run python workbench/scripts/conformance_report.py
```

CI runs the same two commands with `--check`, which fails if the table body differs from the
committed file (the timestamp header is excluded from the comparison).
"""
    return head + body + foot


def table_body(text: str) -> str:
    start, end = text.find(TABLE_START), text.find(TABLE_END)
    return text[start:end] if start >= 0 and end >= 0 else text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", default=str(REPORT))
    ap.add_argument("--reviews", default=str(REVIEWS))
    ap.add_argument("--output", default=str(OUTPUT))
    ap.add_argument(
        "--check", action="store_true", help="exit 1 if the committed table body would change"
    )
    ns = ap.parse_args(argv)
    try:
        register = load_register()
        reviews = load_reviews(register, Path(ns.reviews))
    except RegisterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    text = render(register, load_report(Path(ns.report)), reviews)
    out = Path(ns.output)
    if ns.check:
        if not out.exists() or table_body(out.read_text(encoding="utf-8")) != table_body(text):
            print(
                f"{out.name} is stale; regenerate with scripts/conformance_report.py",
                file=sys.stderr,
            )
            return 1
        print(f"{out.name} is current")
        return 0
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Compare evaluation runs case by case (ADR-0013).

    eval_compare.py OLD NEW                      what changed between two runs
    eval_compare.py --baseline BASELINE.json NEW exit 1 if any case scores lower than the baseline
    eval_compare.py --write-baseline BASELINE.json NEW

OLD and NEW are Inspect log files (`.eval`) or directories, in which case the newest log in the
directory is used. A baseline is the per-case scores of an accepted run plus that run's
identity, committed beside the cases. Change a baseline in a commit of its own, saying why.

Every score is higher-is-better. A score that does not apply to a case (NOANSWER) is recorded as
null and is never a regression.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from inspect_ai.log import EvalLog, read_eval_log

from workbench.evaluation import baseline_of, case_scores, differences, run_identity


def resolve(path: Path) -> Path:
    if path.is_dir():
        logs = sorted(path.glob("*.eval"), key=lambda p: p.stat().st_mtime)
        if not logs:
            sys.exit(f"{path}: no .eval logs")
        return logs[-1]
    return path


def load(path: Path) -> EvalLog:
    log = read_eval_log(str(resolve(path)))
    if log.status != "success":
        sys.exit(f"{path}: the run did not complete ({log.status})")
    return log


def print_identity(old: dict[str, Any], new: dict[str, Any]) -> None:
    for key in sorted(old.keys() | new.keys()):
        a, b = old.get(key), new.get(key)
        print(f"  {key}: {a}" if a == b else f"  {key}: {a} -> {b}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--baseline", type=Path, help="fail if NEW scores below this baseline")
    group.add_argument("--write-baseline", type=Path, help="record NEW as the baseline")
    parser.add_argument("runs", type=Path, nargs="+", help="OLD NEW, or NEW with a baseline")
    args = parser.parse_args(argv)

    if args.baseline or args.write_baseline:
        if len(args.runs) != 1:
            parser.error("give exactly one run with --baseline or --write-baseline")
        new_log = load(args.runs[0])
        if args.write_baseline:
            text = json.dumps(baseline_of(new_log), indent=2, sort_keys=True) + "\n"
            args.write_baseline.write_text(text, encoding="utf-8")
            print(f"wrote {args.write_baseline}")
            return 0
        old = json.loads(args.baseline.read_text(encoding="utf-8"))
        old_ident, old_scores = old["identity"], old["scores"]
        label = str(args.baseline)
    else:
        if len(args.runs) != 2:
            parser.error("give OLD and NEW")
        old_log, new_log = load(args.runs[0]), load(args.runs[1])
        old_ident, old_scores = run_identity(old_log), case_scores(old_log)
        label = str(resolve(args.runs[0]))

    print(f"{label} -> {resolve(args.runs[-1])}")
    print("identity:")
    print_identity(old_ident, run_identity(new_log))
    regressions, changes = differences(old_scores, case_scores(new_log))
    for heading, lines in (("regressions", regressions), ("other changes", changes)):
        print(f"{heading}: {len(lines) or 'none'}")
        for line in lines:
            print(f"  {line}")
    return 1 if args.baseline and regressions else 0


if __name__ == "__main__":
    raise SystemExit(main())

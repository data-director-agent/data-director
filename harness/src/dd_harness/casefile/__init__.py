"""Case files: one run, conversation or project, exported for debugging (docs/specs/casefile.md).

A case is a filtered copy of the stores in the file layout, so `runs/` is a `DD_RUNS_DIR` and
`projects/` a `DD_PROJECTS_DIR` that every reader opens unchanged, with `case.json` naming the
digest of every file, `CASE.md` to read first and `timeline.jsonl` with everything in time order.
`verify` checks a case rather than trusting it.
"""

from __future__ import annotations

from dd_harness.casefile.export import FORMAT, MANIFEST, export
from dd_harness.casefile.select import SCOPES, Selection, select
from dd_harness.casefile.verify import VerifyReport, case_root, verify

__all__ = [
    "FORMAT",
    "MANIFEST",
    "SCOPES",
    "Selection",
    "VerifyReport",
    "case_root",
    "export",
    "select",
    "verify",
]

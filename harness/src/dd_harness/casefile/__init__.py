"""Case files: one run, conversation or project, exported for debugging (docs/specs/casefile.md).

A case is a filtered copy of the stores in the file layout, so `runs/` is a `DD_RUNS_DIR` and
`projects/` a `DD_PROJECTS_DIR` that every reader opens unchanged, with `case.json` naming the
digest of every file, `CASE.md` to read first and `timeline.jsonl` with everything in time order.
`verify` checks a case rather than trusting it. A case can name its content by digest instead of
carrying it (`naming`), and keep the service journal's lines that name it (`journal`).
"""

from __future__ import annotations

from dd_harness.casefile.export import FORMAT, MANIFEST, Options, export
from dd_harness.casefile.journal import Journal, journal_command, read_journal
from dd_harness.casefile.naming import CONTENT, Content, name_content
from dd_harness.casefile.select import SCOPES, Selection, project_log, select
from dd_harness.casefile.verify import VerifyReport, case_root, verify

__all__ = [
    "CONTENT",
    "FORMAT",
    "MANIFEST",
    "SCOPES",
    "Content",
    "Journal",
    "Options",
    "Selection",
    "VerifyReport",
    "case_root",
    "export",
    "journal_command",
    "name_content",
    "project_log",
    "read_journal",
    "select",
    "verify",
]

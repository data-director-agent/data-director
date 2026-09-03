"""The run directory — the audit artefact (C12).

§3 marks C12 as one of two controls that cannot be added later: "cannot be reconstructed after
the fact; the classic thing that never gets added later". So this is written from the first
commit, for a pipeline that is mostly stubs.

Why this exists alongside LangGraph's checkpointer, which also persists every stage: the two
answer different questions. Checkpoints are working memory with a resume capability, in a
format owned by a fast-moving dependency and prunable at will. This directory is the audit
trail — its format is ours, it must survive a serialiser change or a schema rename, and three
things live only here and cannot be recovered from graph state at all: per-call token usage and
timings (they are callback-level and never enter state), raw model responses that failed to
parse, and the verbatim text of every prompt used.

So `stages/NN-*.json` duplicating checkpoint content is the point, not an oversight. A duplicate
you control is what an audit trail is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RUN_FILES = {
    "input": "input.json",
    "profile": "profile.json",
    "recommendations": "recommendations.json",
    "provenance": "prov.jsonld",
    "manifest": "run.json",
    "events": "events.jsonl",
}


class RunDirectory:
    """`runs/<run_id>/`, and the only place anything in it is written."""

    def __init__(self, root: Path, run_id: str) -> None:
        self.run_id = run_id
        self.path = root / run_id
        self.stages_path = self.path / "stages"
        self.prompts_path = self.path / "prompts"
        self.path.mkdir(parents=True, exist_ok=True)
        self.stages_path.mkdir(exist_ok=True)
        self.prompts_path.mkdir(exist_ok=True)

    # -- paths ---------------------------------------------------------------------------

    @property
    def checkpoint_path(self) -> Path:
        return self.path / "checkpoints.sqlite"

    @property
    def events_path(self) -> Path:
        return self.path / RUN_FILES["events"]

    def file(self, key: str) -> Path:
        return self.path / RUN_FILES[key]

    def provenance_relpath(self) -> str:
        """The value written into `RecommendationsDocument.provenance`."""
        return f"runs/{self.run_id}/{RUN_FILES['provenance']}"

    # -- writing -------------------------------------------------------------------------

    def write_json(self, key: str, payload: Any) -> Path:
        path = self.file(key)
        _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return path

    def write_stage(self, index: int, stage: str, payload: Any) -> Path:
        """Write one stage's report and output. `index` is 1-based, so files sort in order."""
        path = self.stages_path / f"{index:02d}-{stage}.json"
        _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return path

    def copy_prompt(self, name: str, version: str, text: str) -> Path:
        """Keep the verbatim prompt text with the run.

        Without this, reading a six-month-old run means git archaeology to find out what the
        model was actually asked — and that assumes the file was never deleted.
        """
        path = self.prompts_path / f"{name}.{version}.md"
        _atomic_write_text(path, text)
        return path

    def append_event(self, event: dict[str, Any]) -> None:
        """Append one line to the event log. Append-only, never rewritten (§4.1)."""
        line = json.dumps(event, sort_keys=True, default=str)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    # -- reading -------------------------------------------------------------------------

    def read_json(self, key: str) -> Any:
        path = self.file(key)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def read_events(self) -> list[dict[str, Any]]:
        if not self.events_path.is_file():
            return []
        events: list[dict[str, Any]] = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events


def _atomic_write_text(path: Path, text: str) -> None:
    """Write via a temporary file and rename.

    A half-written provenance record is worse than a missing one — it reads as complete.
    """
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)

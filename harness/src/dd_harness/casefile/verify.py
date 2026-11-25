"""Check a case rather than trust it (docs/specs/casefile.md, Verification): every file against
the digest `case.json` names, every envelope against the contract, every input hash against the
stored request, and every grounding report against the linter run again over the stored trace.
Evidence that cites a source outside the case is not fetched again; the report says so.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dd_harness import grounding
from dd_harness.casefile.copy import RUNS
from dd_harness.casefile.export import FORMAT, MANIFEST, file_digests
from dd_harness.storage import GROUNDING, SPANS, WITHHELD
from dd_harness.store import RunStore
from dd_sdk.contract.validate import ContractViolation, validate_envelope
from dd_sdk.evidence import input_hash
from dd_sdk.tracing import ATTR_INPUT_HASH, INVOKE_AGENT, SpanRecord, records_from_jsonl

NOT_FETCHED = "evidence citing a source outside the case is not fetched again"
NAMED = (
    "content is named, so no envelope is checked against the contract, no input hash against "
    "its request and no grounding report against the linter"
)


@dataclass(frozen=True)
class Check:
    """One check: what it is about, whether it passed and, if not, why."""

    about: str
    passed: bool
    detail: str = ""


@dataclass
class VerifyReport:
    checks: list[Check] = field(default_factory=list)
    # What the case could not be checked for, and why.
    not_checked: list[str] = field(default_factory=lambda: [NOT_FETCHED])
    # The SHA-256 of its `case.json`, which names the whole case, once it is read.
    digest: str | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def add(self, about: str, problem: str | None) -> None:
        self.checks.append(Check(about, problem is None, problem or ""))

    def summary(self) -> str:
        failed = [c for c in self.checks if not c.passed]
        lines = [f"case: {'passed' if not failed else 'failed'} ({len(self.checks)} checks)"]
        if self.digest is not None:
            lines.append(f"  case.json sha256:{self.digest}")
        lines += [f"  failed: {c.about}: {c.detail}" for c in failed]
        lines += [f"  not checked: {reason}" for reason in self.not_checked]
        return "\n".join(lines)


@contextmanager
def case_root(path: Path) -> Iterator[Path]:
    """The case at `path` as a directory: itself, or a zip unpacked for as long as it is used."""
    if path.is_dir():
        yield path
        return
    with tempfile.TemporaryDirectory() as scratch, zipfile.ZipFile(path) as archive:
        archive.extractall(scratch)
        yield Path(scratch)


def _files(root: Path, manifest: dict[str, Any]) -> str | None:
    named, found = manifest.get("files") or {}, file_digests(root)
    if named == found:
        return None
    changed = sorted(p for p in named.keys() & found.keys() if named[p] != found[p])
    missing, extra = sorted(named.keys() - found.keys()), sorted(found.keys() - named.keys())
    return f"changed {changed}, missing {missing}, not named {extra}"


def _spans(store: RunStore, invocation_id: str) -> list[SpanRecord] | None:
    data = store.get_artifact(invocation_id, SPANS)
    if data is None:
        return None
    return records_from_jsonl([json.loads(line) for line in data.decode().splitlines() if line])


def _input_hash(store: RunStore, envelope: dict[str, Any]) -> str | None:
    """The input hash the conductor set on the run's root span is the hash of the stored request's
    input (docs/specs/transport.md, invariant 7)."""
    request = store.get_request(envelope["invocation_id"])
    records = _spans(store, envelope["invocation_id"])
    if request is None or records is None:
        return None
    roots = [r for r in records if r.name == INVOKE_AGENT and ATTR_INPUT_HASH in r.attributes]
    if not roots:
        return None
    if roots[0].attributes[ATTR_INPUT_HASH] != input_hash(request["input"]):
        return "the trace's input hash is not the hash of the stored request's input"
    return None


def _grounding(store: RunStore, envelope: dict[str, Any]) -> str | None:
    """The linter over the stored trace reports what the run stored. A withheld result was
    linted before it was withheld, so the linter reads it."""
    invocation_id = envelope["invocation_id"]
    stored = store.get_artifact(invocation_id, GROUNDING)
    records = _spans(store, invocation_id)
    if stored is None or records is None:
        return None
    withheld = store.get_artifact(invocation_id, WITHHELD)
    linted = json.loads(withheld) if withheld is not None else envelope
    again = grounding.lint(records, linted).summary()
    if again != stored.decode().strip():
        return f"the linter now reports {again!r}"
    return None


def _envelope(store: RunStore, envelope: dict[str, Any], report: VerifyReport) -> None:
    run = f"run {envelope['invocation_id']}"
    try:
        validate_envelope(envelope)
        report.add(f"{run} contract", None)
    except ContractViolation as exc:
        report.add(f"{run} contract", "; ".join(exc.messages))
    report.add(f"{run} input hash", _input_hash(store, envelope))
    report.add(f"{run} grounding", _grounding(store, envelope))


def verify(path: Path) -> VerifyReport:
    """Every check of the case at `path`, a directory or zip."""
    report = VerifyReport()
    with case_root(path) as root:
        manifest_path = root / MANIFEST
        if not manifest_path.is_file():
            report.add("manifest", f"no {MANIFEST}")
            return report
        report.digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format") != FORMAT:
            report.add("manifest", f"format {manifest.get('format')!r} is not {FORMAT!r}")
            return report
        report.add("files", _files(root, manifest))
        if manifest.get("content") == "named":
            report.not_checked = [NAMED]
        elif (root / RUNS).is_dir():
            store = RunStore(root / RUNS)
            for envelope in store.iter_envelopes():
                _envelope(store, envelope, report)
    return report

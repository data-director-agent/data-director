"""The source check: cited records re-hashed against an independent copy of the source (ADR-0016).

The grounding linter (ADR-0008) compares an agent's account of its run with itself and with what
the conductor recorded. A `retrieval` span is written in the agent's process and sent back over
A2A (ADR-0011), so G1-G3 show that the agent's claims agree with one another, not that it read
anything. The source check closes part of that gap. For each evidence item, it looks up the
cited `source_id` in a copy of the source the workbench holds, projects that record under the
evidence's `canonicalisation` (ADR-0009), and compares the hash:

  S1 the source the evidence names holds a record with that `source_id`.
  S2 that record hashes to the evidence's `content_hash`. With E1 (ADR-0015), what a reader is
     shown about a cited record is then the source's own projection of it.

An evidence item is resolved by its `snapshot_ref`. One the workbench holds no copy of is
*unresolved*: that is not a violation, and it is never counted as verified. In the modes whose
rules hold every citation to the input or a recorded delegation (R2, D1, D2), evidence citing
`input:` or `invocation:` is skipped, because the linter has already checked it against hashes
the conductor computed. In `retrieval` mode no rule does that, so such evidence is unresolved.

What the check does not show: when, or whether, the agent read the record during the run. That
would need retrieval to go through the workbench, as delegation does. TODO (ADR-0016).

A copy is independent of the agent because its bytes are pinned by `sha256` in `sources.yaml`,
not because of where the file lives. A file that does not match its pin is a configuration
error. Configuration shape:

    sources:
      - snapshot_refs: ["snapshot:2026-09-04"]   # evidence snapshot_ref values this copy serves
        path: ../agents/r3/data/fairsharing/snapshot.jsonl   # relative to this file
        id_field: fairsharing_id                 # the record field that is the source_id
        sha256: 9696…                            # of the file's bytes

A file is JSON Lines, or one JSON array of records.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from dd_sdk.contract.models import GroundingMode, input_source_id, invocation_source_id
from dd_sdk.evidence import content_hash

# The prefixes of source ids whose hashes the conductor computed itself, and the grounding modes
# whose linter rules check them against those hashes.
ATTESTED_PREFIXES = (input_source_id(""), invocation_source_id(""))
ATTESTED_MODES = (GroundingMode.INPUT_ONLY, GroundingMode.NONE, GroundingMode.DELEGATION)


class SourceConfigError(Exception):
    """`sources.yaml` is malformed, or a file it lists is missing or does not match its pin."""


class Resolver(Protocol):
    def record(self, source_id: str) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class RecordsFile:
    """The records of one pinned file, indexed by `id_field`."""

    records: Mapping[str, dict[str, Any]]

    @classmethod
    def load(cls, path: Path, id_field: str, sha256: str) -> RecordsFile:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise SourceConfigError(f"source file {path}: {exc}") from None
        actual = hashlib.sha256(raw).hexdigest()
        if actual != sha256:
            raise SourceConfigError(
                f"source file {path} has sha256 {actual}, not the pinned {sha256}"
            )
        text = raw.decode("utf-8")
        if text.lstrip().startswith("["):
            rows = json.loads(text)
        else:
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        index: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get(id_field), str):
                raise SourceConfigError(f"source file {path}: a record has no string {id_field!r}")
            index[row[id_field]] = row
        return cls(records=index)

    def record(self, source_id: str) -> dict[str, Any] | None:
        return self.records.get(source_id)


@dataclass(frozen=True)
class SourceReport:
    verified: int = 0
    unresolved: list[str] = field(default_factory=list)  # "<source_id> (<snapshot_ref>)"
    violations: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations

    def summary(self) -> str:
        head = f"sources: {self.verified} verified, {len(self.unresolved)} unresolved"
        if self.unresolved:
            head += " (no independent copy: " + ", ".join(self.unresolved) + ")"
        if self.passed:
            return head
        return f"{head}; FAILED\n  - " + "\n  - ".join(self.violations)


@dataclass(frozen=True)
class Sources:
    """The copies of sources the workbench holds, keyed by the `snapshot_ref` they serve."""

    by_snapshot_ref: Mapping[str, Resolver] = field(default_factory=dict)

    @classmethod
    def none(cls) -> Sources:
        return cls()

    @classmethod
    def from_config(cls, path: Path) -> Sources:
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise SourceConfigError(f"cannot read {path}: {exc}") from None
        entries = doc.get("sources") if isinstance(doc, dict) else None
        if not isinstance(entries, list):
            raise SourceConfigError(f"{path}: expected a top-level 'sources' list")
        by_ref: dict[str, Resolver] = {}
        for entry in entries:
            try:
                refs, file, id_field, pin = (
                    entry["snapshot_refs"],
                    entry["path"],
                    entry["id_field"],
                    entry["sha256"],
                )
            except KeyError, TypeError:
                raise SourceConfigError(
                    f"{path}: each source needs snapshot_refs, path, id_field and sha256"
                ) from None
            resolver = RecordsFile.load(path.parent / str(file), str(id_field), str(pin))
            for ref in refs:
                if ref in by_ref:
                    raise SourceConfigError(f"{path}: snapshot_ref {ref!r} is listed twice")
                by_ref[str(ref)] = resolver
        return cls(by_snapshot_ref=by_ref)


def check(envelope: dict[str, Any], sources: Sources) -> SourceReport:
    """Re-hash every externally sourced evidence item against the workbench's copy."""
    verified = 0
    unresolved: list[str] = []
    violations: list[str] = []
    attested = envelope.get("grounding_mode") in {m.value for m in ATTESTED_MODES}
    for ev in envelope.get("evidence") or []:
        source_id = str(ev.get("source_id"))
        if attested and source_id.startswith(ATTESTED_PREFIXES):
            continue
        snapshot_ref = ev.get("snapshot_ref")
        resolver = sources.by_snapshot_ref.get(str(snapshot_ref))
        if resolver is None:
            unresolved.append(f"{source_id} ({snapshot_ref})")
            continue
        record = resolver.record(source_id)
        if record is None:
            violations.append(
                f"S1: evidence cites {source_id!r}, which {snapshot_ref!r} does not hold"
            )
            continue
        expected = str(ev.get("content_hash"))
        try:
            actual = content_hash(record, str(ev.get("canonicalisation")))
        except ValueError as exc:
            violations.append(f"S2: evidence {source_id!r}: {exc}")
            continue
        if actual != expected:
            violations.append(
                f"S2: evidence {source_id!r} hash {expected[:12]}… does not match "
                f"{snapshot_ref!r}, where the record hashes to {actual[:12]}…"
            )
            continue
        verified += 1
    return SourceReport(verified=verified, unresolved=unresolved, violations=violations)

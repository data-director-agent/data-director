"""The source check: cited records re-hashed against an independent copy of the source
(docs/specs/grounding.md).

The grounding linter (docs/specs/grounding.md) compares an agent's account of its run with itself
and with what the conductor recorded. A `retrieval` span is written in the agent's process and sent
back over A2A (docs/specs/agents.md), so G1-G3 show that the agent's claims agree with one another,
not that it read anything. The source check closes part of that gap. For each evidence item, it
looks up the cited `source_id` in a copy of the source the harness holds, projects that record under
the evidence's `canonicalisation` (docs/specs/grounding.md), and compares the hash:

  S1 the source the evidence names holds a record with that `source_id`. S2 that record hashes to
  the evidence's `content_hash`. With E1 (docs/specs/grounding.md), what a reader is
     shown about a cited record is then the source's own projection of it.

An evidence item is resolved by its `snapshot_ref`. One the harness holds no copy of is
*unresolved*: that is not a violation, and it is never counted as verified. In the modes whose
rules hold every citation to the input or a recorded delegation (R2, D1, D2), evidence citing
`input:` or `invocation:` is skipped, because the linter has already checked it against hashes
the conductor computed. In `retrieval` mode no rule does that, so such evidence is unresolved.

What the check does not show: when, or whether, the agent read the record during the run. That would
need retrieval to go through the harness, as delegation does. TODO(#246) (docs/specs/grounding.md).

A copy is independent of the agent because its bytes are pinned by `sha256` in `sources.yaml`,
not because of where the file lives. A file that does not match its pin is a configuration
error, and so is a missing one, unless its entry says it is built outside git (`built: true`):
such a copy, if it has not been built, is logged with the one command that builds every agent's
sources (`dd-sources prepare`, dd_sdk.sources), and evidence citing it is unresolved, so a
deployment that serves no agent citing it need not build it. How a copy is built is its agent's
business, not this file's.
Configuration shape:

    sources:
      - snapshot_refs: ["snapshot:2026-09-04"]   # evidence snapshot_ref values this copy serves
        path: ../agents/advisor-standards/data/fairsharing/snapshot.jsonl   # relative to this file
        id_field: fairsharing_id                 # the record field that is the source_id
        sha256: 9696…                            # of the file's bytes
        built: true                              # optional: the copy is built, not kept in git

A file is JSON Lines, or one JSON array of records.

The same copies answer one other question: what re3data says about a repository a researcher
chooses (docs/specs/deposit.md). `Sources.re3data` reads the latest re3data export pinned under
`re3data:export:YYYY-MM` and returns the record with the hash a citation of it would carry.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from dd_sdk.contract.models import GroundingMode, input_source_id, invocation_source_id
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash
from dd_sdk.sources import PREPARE_COMMAND

# The prefixes of source ids whose hashes the conductor computed itself, and the grounding modes
# whose linter rules check them against those hashes.
ATTESTED_PREFIXES = (input_source_id(""), invocation_source_id(""))
ATTESTED_MODES = (GroundingMode.INPUT_ONLY, GroundingMode.NONE, GroundingMode.DELEGATION)

# The snapshot_ref prefix of a pinned monthly re3data export, followed by its month (YYYY-MM).
RE3DATA_EXPORT = "re3data:export:"

log = logging.getLogger(__name__)


class SourceConfigError(Exception):
    """`sources.yaml` is malformed, or a file it lists does not match its pin, or is missing and
    names no command that builds it."""


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
class RegistryEntry:
    """What a pinned re3data export says about one repository, and which record said it."""

    re3data_id: str
    name: str
    metadata_standards: tuple[str, ...]
    snapshot_ref: str
    content_hash: str
    canonicalisation: str = DOCUMENT_CANONICALISATION


@dataclass(frozen=True)
class Sources:
    """The copies of sources the harness holds, keyed by the `snapshot_ref` they serve."""

    by_snapshot_ref: Mapping[str, Resolver] = field(default_factory=dict)
    # The snapshot_refs of copies built outside git that have not been built. Evidence citing one
    # is unresolved.
    unbuilt: frozenset[str] = frozenset()

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
        unbuilt: set[str] = set()
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
            refs = [str(ref) for ref in refs]
            for ref in refs:
                if ref in by_ref or ref in unbuilt:
                    raise SourceConfigError(f"{path}: snapshot_ref {ref!r} is listed twice")
            built = entry.get("built", False)
            if not isinstance(built, bool):
                raise SourceConfigError(f"{path}: 'built' must be true or false, not {built!r}")
            if built and not (path.parent / str(file)).is_file():
                log.warning(
                    "%s: source file %s is not built, so evidence citing %s will be unresolved; "
                    "build it with `%s`",
                    path,
                    file,
                    ", ".join(refs),
                    PREPARE_COMMAND,
                )
                unbuilt.update(refs)
                continue
            resolver = RecordsFile.load(path.parent / str(file), str(id_field), str(pin))
            by_ref.update(dict.fromkeys(refs, resolver))
        return cls(by_snapshot_ref=by_ref, unbuilt=frozenset(unbuilt))

    def re3data(self, re3data_id: str) -> RegistryEntry | None:
        """The record the latest pinned re3data export holds for `re3data_id`, or `None` if it
        holds none. Raises `SourceConfigError` if no export is pinned or the latest is not built.
        """
        refs = sorted(
            ref for ref in (*self.by_snapshot_ref, *self.unbuilt) if ref.startswith(RE3DATA_EXPORT)
        )
        if not refs:
            raise SourceConfigError(
                f"sources.yaml pins no re3data export ({RE3DATA_EXPORT}YYYY-MM), so a repository "
                "cannot be looked up"
            )
        ref = refs[-1]
        resolver = self.by_snapshot_ref.get(ref)
        if resolver is None:
            raise SourceConfigError(
                f"the re3data export {ref} is not built; build it with `{PREPARE_COMMAND}`"
            )
        record = resolver.record(re3data_id)
        if record is None:
            return None
        name, standards = record.get("name"), record.get("metadata_standards") or []
        if not isinstance(name, str) or not all(isinstance(s, str) for s in standards):
            raise SourceConfigError(
                f"{ref}: the record of {re3data_id} has no name or a malformed metadata_standards"
            )
        return RegistryEntry(
            re3data_id=re3data_id,
            name=name,
            metadata_standards=tuple(standards),
            snapshot_ref=ref,
            content_hash=content_hash(record, DOCUMENT_CANONICALISATION),
        )


def check(envelope: dict[str, Any], sources: Sources) -> SourceReport:
    """Re-hash every externally sourced evidence item against the harness's copy."""
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
            why = ", not built" if str(snapshot_ref) in sources.unbuilt else ""
            unresolved.append(f"{source_id} ({snapshot_ref}{why})")
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

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
`Sources.find_repositories` searches the same export by name or by the repository's own
identifiers (its re3data identifier, its re3data DOI or its URL), so that a researcher can choose
one without an advisor's shortlist; the same query always gives the same answer.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

import yaml

from dd_sdk.contract.models import (
    RE3DATA_ID_PATTERN,
    TOOL_SOURCE_PREFIX,
    GroundingMode,
    input_source_id,
    invocation_source_id,
)
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash
from dd_sdk.sources import PREPARE_COMMAND

# The prefixes of source ids whose hashes the conductor computed itself, and the grounding modes
# whose linter rules check them against those hashes.
ATTESTED_PREFIXES = (input_source_id(""), invocation_source_id(""))
ATTESTED_MODES = (GroundingMode.INPUT_ONLY, GroundingMode.NONE, GroundingMode.DELEGATION)

# The snapshot_ref prefix of a pinned monthly re3data export, followed by its month (YYYY-MM).
RE3DATA_EXPORT = "re3data:export:"
# The snapshot_ref prefix of a pinned snapshot of the repositories DataCite registers that re3data
# does not list, followed by the day it was fetched (agents/advisor-repository/data/datacite).
DATACITE_REPOSITORIES = "datacite:repositories:"
# Every repository in that snapshot registers DataCite DOIs, so it declares DataCite's standard,
# by the name re3data gives it (app/config/repositories/standards/datacite-4.yaml).
DATACITE_STANDARD = "DataCite Metadata Schema"
_RE3DATA_ID = re.compile(RE3DATA_ID_PATTERN)
# A query shorter than this, once trimmed, matches no name (it would match most of them).
MIN_QUERY = 2
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", re.IGNORECASE)
_URL_PREFIX = re.compile(r"^(?:https?://)?(?:www\.)?", re.IGNORECASE)

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
    """What a pinned registry says about one repository, and which record said it:
    `repository_id` is its re3data identifier, or its DataCite one where re3data lists it under
    none (`re3data_id` is then None)."""

    repository_id: str
    re3data_id: str | None
    name: str
    metadata_standards: tuple[str, ...]
    snapshot_ref: str
    content_hash: str
    canonicalisation: str = DOCUMENT_CANONICALISATION


@dataclass(frozen=True)
class RepositoryMatch:
    """What a search of the pinned registries shows of one repository: `registry` is `re3data`
    or `datacite`, and `re3data_id` is None for a repository only DataCite registers."""

    repository_id: str
    name: str
    additional_names: tuple[str, ...] = ()
    url: str | None = None
    doi: str | None = None
    registry: str = "re3data"

    @property
    def re3data_id(self) -> str | None:
        return self.repository_id if self.registry == "re3data" else None

    @classmethod
    def of(cls, record: Mapping[str, Any]) -> RepositoryMatch:
        if "datacite_id" in record:
            alternate = record.get("alternate_name")
            url = record.get("url")
            return cls(
                repository_id=str(record["datacite_id"]),
                name=str(record.get("name") or record["datacite_id"]),
                additional_names=(alternate,) if isinstance(alternate, str) else (),
                url=url if isinstance(url, str) else None,
                registry="datacite",
            )
        names = record.get("additional_names") or []
        url, doi = record.get("url"), record.get("doi")
        return cls(
            repository_id=str(record["re3data_id"]),
            name=str(record.get("name") or record["re3data_id"]),
            additional_names=tuple(str(n) for n in names if isinstance(n, str)),
            url=url if isinstance(url, str) else None,
            doi=doi if isinstance(doi, str) else None,
        )

    def describe(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "registry": self.registry,
            "re3data_id": self.re3data_id,
            "name": self.name,
            "additional_names": list(self.additional_names),
            "url": self.url,
            "doi": self.doi,
        }


def _bare_doi(value: str) -> str:
    return _DOI_PREFIX.sub("", value.strip()).casefold()


def _bare_url(value: str) -> str:
    return _URL_PREFIX.sub("", value.strip()).rstrip("/").casefold()


def _identifies(query: str, record: Mapping[str, Any]) -> bool:
    """Whether `query` is one of the repository's own identifiers. An institution's ROR is not:
    it names an organisation, not a repository."""
    if _RE3DATA_ID.fullmatch(query.casefold()):
        return record.get("re3data_id") == query.casefold()
    if record.get("datacite_id") == query.strip().casefold():
        return True
    doi, url = record.get("doi"), record.get("url")
    if isinstance(doi, str) and doi and _bare_doi(doi) == _bare_doi(query):
        return True
    return isinstance(url, str) and bool(_bare_url(url)) and _bare_url(url) == _bare_url(query)


def _names(record: Mapping[str, Any]) -> list[str]:
    names = [
        record.get("name"),
        record.get("alternate_name"),
        *(record.get("additional_names") or []),
    ]
    return [n.casefold() for n in names if isinstance(n, str)]


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

    def with_resolvers(self, more: Mapping[str, Resolver]) -> Sources:
        """These copies and `more`, such as what the profile vouches for, by `snapshot_ref`."""
        if not more:
            return self
        return replace(self, by_snapshot_ref={**self.by_snapshot_ref, **more})

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

    def _latest(self, prefix: str) -> tuple[str, Resolver] | None:
        """The latest pinned copy whose `snapshot_ref` starts with `prefix`, or None if none is
        pinned. Raises `SourceConfigError` if the latest is not built."""
        refs = sorted(
            ref for ref in (*self.by_snapshot_ref, *self.unbuilt) if ref.startswith(prefix)
        )
        if not refs:
            return None
        resolver = self.by_snapshot_ref.get(refs[-1])
        if resolver is None:
            raise SourceConfigError(
                f"the copy {refs[-1]} is not built; build it with `{PREPARE_COMMAND}`"
            )
        return refs[-1], resolver

    def _re3data_export(self) -> tuple[str, Resolver]:
        """The latest pinned re3data export and its `snapshot_ref`. Raises `SourceConfigError` if
        none is pinned or the latest is not built."""
        found = self._latest(RE3DATA_EXPORT)
        if found is None:
            raise SourceConfigError(
                f"sources.yaml pins no re3data export ({RE3DATA_EXPORT}YYYY-MM), so a repository "
                "cannot be looked up"
            )
        return found

    def _datacite(self) -> tuple[str, RecordsFile] | None:
        """The latest pinned DataCite snapshot, less the repositories whose address is a
        re3data record's, which re3data describes; None if none is pinned."""
        found = self._latest(DATACITE_REPOSITORIES)
        if found is None or not isinstance(found[1], RecordsFile):
            return None
        _, re3data = self._re3data_export()
        listed = (
            {_bare_url(u) for r in re3data.records.values() if isinstance(u := r.get("url"), str)}
            if isinstance(re3data, RecordsFile)
            else set()
        )
        kept = {
            k: r
            for k, r in found[1].records.items()
            if not isinstance(u := r.get("url"), str) or _bare_url(u) not in listed
        }
        return found[0], RecordsFile(records=kept)

    def re3data_export_ref(self) -> str:
        """The `snapshot_ref` of the export `re3data` and `find_repositories` read."""
        return self._re3data_export()[0]

    def find_repositories(self, query: str, limit: int = 20) -> list[RepositoryMatch]:
        """The repositories in the latest pinned re3data export, and DataCite snapshot, that
        `query` names, at most `limit` of them. A repository `query` identifies (its re3data or
        DataCite identifier, its re3data DOI or its URL) comes first; then those with a name or
        additional name that starts with it; then those with one that contains it. Each group
        is in order of name, then identifier. Raises `SourceConfigError` as `re3data` does."""
        ref, resolver = self._re3data_export()
        if not isinstance(resolver, RecordsFile):
            raise SourceConfigError(f"the re3data export {ref} cannot be searched")
        wanted = query.strip()
        if not wanted:
            return []
        datacite = self._datacite()
        records = [*resolver.records.values(), *(datacite[1].records.values() if datacite else [])]
        folded = wanted.casefold()
        groups: tuple[list[Mapping[str, Any]], ...] = ([], [], [])
        for record in records:
            names = _names(record)
            if _identifies(wanted, record):
                groups[0].append(record)
            elif len(folded) < MIN_QUERY:
                continue
            elif any(n.startswith(folded) for n in names):
                groups[1].append(record)
            elif any(folded in n for n in names):
                groups[2].append(record)
        found: list[RepositoryMatch] = []
        for group in groups:
            matches = sorted(
                (RepositoryMatch.of(r) for r in group),
                key=lambda m: (m.name.casefold(), m.repository_id),
            )
            found.extend(matches)
        return found[: max(limit, 0)]

    def repositories(self, repository_ids: Sequence[str]) -> list[RepositoryMatch]:
        """The repositories the pinned registries hold of `repository_ids`, in that order,
        without those they do not hold. Raises `SourceConfigError` as `re3data` does."""
        found = (self._record(i) for i in dict.fromkeys(repository_ids))
        return [RepositoryMatch.of(r[1]) for r in found if r is not None]

    def _record(self, repository_id: str) -> tuple[str, dict[str, Any]] | None:
        if _RE3DATA_ID.fullmatch(repository_id):
            ref, resolver = self._re3data_export()
        elif (datacite := self._datacite()) is not None:
            ref, resolver = datacite
        else:
            return None
        record = resolver.record(repository_id)
        return None if record is None else (ref, record)

    def repository(self, repository_id: str) -> RegistryEntry | None:
        """The record the latest pinned registry holds for `repository_id`: re3data's for a
        re3data identifier, else DataCite's; `None` if it holds none. A DataCite repository
        declares DataCite's standard, whose DOIs it registers. Raises `SourceConfigError` if no
        re3data export is pinned or the latest is not built."""
        found = self._record(repository_id)
        if found is None:
            return None
        ref, record = found
        listed = _RE3DATA_ID.fullmatch(repository_id) is not None
        name = record.get("name")
        standards = (record.get("metadata_standards") or []) if listed else [DATACITE_STANDARD]
        if not isinstance(name, str) or not all(isinstance(s, str) for s in standards):
            raise SourceConfigError(
                f"{ref}: the record of {repository_id} has no name or a malformed "
                "metadata_standards"
            )
        return RegistryEntry(
            repository_id=repository_id,
            re3data_id=repository_id if listed else None,
            name=name,
            metadata_standards=tuple(standards),
            snapshot_ref=ref,
            content_hash=content_hash(record, DOCUMENT_CANONICALISATION),
        )

    def re3data(self, re3data_id: str) -> RegistryEntry | None:
        """The record the latest pinned re3data export holds for `re3data_id`, or `None`."""
        return self.repository(re3data_id) if _RE3DATA_ID.fullmatch(re3data_id) else None


def check(envelope: dict[str, Any], sources: Sources) -> SourceReport:
    """Re-hash every externally sourced evidence item against the harness's copy. A record the
    conductor kept from the tool gateway is its own observation (docs/specs/grounding.md,
    invariant 15), and is not looked up again."""
    verified = 0
    unresolved: list[str] = []
    violations: list[str] = []
    attested = envelope.get("grounding_mode") in {m.value for m in ATTESTED_MODES}
    from_gateway = {
        (str(r.get("source_id")), str(r.get("content_hash")))
        for r in envelope.get("tool_retrievals") or []
        if isinstance(r, dict)
    }
    for ev in envelope.get("evidence") or []:
        source_id = str(ev.get("source_id"))
        if attested and source_id.startswith(ATTESTED_PREFIXES):
            continue
        if source_id.startswith(TOOL_SOURCE_PREFIX) and (
            (source_id, str(ev.get("content_hash"))) in from_gateway
        ):
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

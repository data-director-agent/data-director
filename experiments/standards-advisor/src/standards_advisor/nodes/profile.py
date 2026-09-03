"""Stage 1 — profile (§5.1). The one genuinely implemented stage at v0.1.

Turns whatever the researcher has into a structured description of the dataset. It is the only
stage that touches file contents, and everything the later stages search on comes from here — so
a profiling mistake shows up as a retrieval mistake unless the profile records how each of its
own statements was arrived at. Every field it writes therefore carries a `Derivation`.

Only **tier 1** runs: formats, headers, column types, counts. All local, no model. §1.4 makes
that a design constraint rather than a property of this prototype's test data — the parts that
read file contents run locally with no model involved, and only derived column *metadata* is
ever eligible to be sent to a model. Tiers 2 and 3 are explicit early returns below.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from standards_advisor import __version__
from standards_advisor.ids import sha256_file_head, utc_now
from standards_advisor.models.common import Derivation, StageName, StageStatus, Term
from standards_advisor.models.profile import (
    ContentFingerprint,
    DatasetProfile,
    FileEntry,
    SourceRef,
)
from standards_advisor.nodes.support import merge, stage
from standards_advisor.profiling import columns as column_inference
from standards_advisor.profiling import files as file_detection
from standards_advisor.profiling import tabular

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

    from standards_advisor.context import RunContext
    from standards_advisor.state import PipelineState


def profile_node(state: PipelineState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = runtime.context
    inputs = state["inputs"]

    with stage(ctx, StageName.PROFILE) as run:
        paths = [Path(item) for item in inputs.files]
        readable = [path for path in paths if path.is_file()]
        for path in paths:
            if not path.is_file():
                # A bad path is a fact about the input, not a crash (see `errors`).
                run.fail("input_missing", f"{path} is not a readable file")

        metadata = _load_metadata(inputs.metadata_path, run)

        file_entries: list[FileEntry] = []
        column_profiles = []
        for readable_path in readable:
            entry, entry_columns = _profile_file(readable_path, ctx.head_rows)
            file_entries.append(entry)
            column_profiles.extend(entry_columns)

        # Tier 2 (subject, field of research, entity scope from the registry's own lists) and
        # tier 3 (measured variables from free text) are not implemented. Both need the
        # registry's term lists, which no v0.1 route can fetch; hard-coding them would breach
        # R3.5 in the first commit. See §5.1 and registry/fairsharing.py.
        subjects: list[Term] = _subjects_from_metadata(metadata, inputs)
        run.note("tier 2 (registry-list subjects) not implemented at v0.1 — see §5.1")
        run.note("tier 3 (measured variables from description) not implemented at v0.1 — §5.1")

        formats = sorted({entry.format for entry in file_entries if entry.format})

        profile = DatasetProfile(
            profile_id=f"{state['run_id']}-profile",
            fingerprint=_fingerprint(readable),
            source=SourceRef(
                kind="local_files",
                locations=[str(path) for path in readable],
                metadata_record=inputs.metadata_path,
            ),
            profiled_at=utc_now().isoformat(),
            profiler_version=__version__,
            title=inputs.title or _text(metadata, "title"),
            abstract=inputs.description or _text(metadata, "description"),
            keywords=inputs.keywords or _keywords(metadata),
            subjects=subjects,
            fields_of_research=[],
            entity_scope=[],
            files=file_entries,
            columns=column_profiles,
            measured_variables=[],
            target_repository=inputs.target_repository or _text(metadata, "publisher"),
            formats_found=formats,
        )

        run.payload = profile
        run.counts = {
            "files": len(file_entries),
            "columns": len(column_profiles),
            "rows_sampled": sum(entry.rows_sampled or 0 for entry in file_entries),
        }
        if not file_entries:
            run.status = StageStatus.EMPTY

        ctx.run_dir.write_json("profile", profile.model_dump(mode="json"))

    return merge(run, profile=run.payload)


def _profile_file(path: Path, head_rows: int) -> tuple[FileEntry, list[Any]]:
    """Detect one file's format and, if it is tabular, profile its columns."""
    format_label, derivation, notes = file_detection.resolve_format(path)
    tabular_file = file_detection.is_tabular(format_label)
    size = path.stat().st_size

    if not tabular_file:
        return (
            FileEntry(
                path=str(path),
                format=format_label,
                format_derivation=derivation,
                size_bytes=size,
                rows_sampled=None,
                is_tabular=False,
                notes=notes,
            ),
            [],
        )

    head = tabular.read_head(path, max_rows=head_rows)
    profiles = [
        column_inference.profile_column(
            name=name,
            position=index,
            file=str(path),
            values=head.columns[name],
            # False always: the pipeline only ever sees the head of a file, so every count
            # here is a sample statistic and must not be mistaken for a population one.
            exact_counts=False,
        )
        for index, name in enumerate(head.headers)
    ]
    return (
        FileEntry(
            path=str(path),
            format=format_label,
            format_derivation=derivation,
            media_type="text/csv" if format_label == "csv" else None,
            size_bytes=size,
            rows_sampled=head.rows_read,
            is_tabular=True,
            notes=[*notes, *head.notes, f"delimiter {head.delimiter!r}"],
        ),
        profiles,
    )


def _fingerprint(paths: list[Path]) -> ContentFingerprint:
    """A stable digest over the inputs, for C17 caching later."""
    combined = hashlib.sha256()
    total = 0
    for path in sorted(paths):
        digest, size = sha256_file_head(path)
        combined.update(path.name.encode("utf-8"))
        combined.update(digest.encode("ascii"))
        total += size
    return ContentFingerprint(
        digest=combined.hexdigest(), total_bytes=total, files_hashed=len(paths)
    )


def _load_metadata(metadata_path: str | None, run: Any) -> dict[str, Any]:
    """Read a supplied metadata record. A malformed one is recorded, not raised.

    C5 asks that we accept the metadata a general-purpose repository such as FigShare or Zenodo
    already provides, so the reader is deliberately lenient about which fields are present.
    """
    if metadata_path is None:
        return {}
    path = Path(metadata_path)
    if not path.is_file():
        run.fail("metadata_missing", f"{metadata_path} is not a readable file")
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        run.fail("metadata_unparseable", f"{metadata_path}: {exc}")
        return {}
    if not isinstance(loaded, dict):
        run.fail("metadata_unexpected", f"{metadata_path} is not a JSON object")
        return {}
    return loaded


def _text(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _keywords(metadata: dict[str, Any]) -> list[str]:
    value = metadata.get("keywords")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _subjects_from_metadata(metadata: dict[str, Any], inputs: Any) -> list[Term]:
    """Subjects taken straight from supplied metadata, marked as such.

    These are *not* registry terms, and the `Derivation` says so: `SUPPLIED_METADATA` with no
    `list_name`. That distinction is what keeps R3.5 honest — a keyword a depositor typed is not
    a term from a controlled list, and the §5.3 subject rule must be able to tell the
    difference.
    """
    raw = metadata.get("subjects")
    terms = [item for item in raw if isinstance(item, str)] if isinstance(raw, list) else []
    return [
        Term(term=term, list_name=None, list_version=None, derivation=Derivation.SUPPLIED_METADATA)
        for term in terms
    ]

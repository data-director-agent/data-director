"""advisor.files: the File Archivist persona (ADR-0033). A mock.

Serves `preparation.files`. It takes the names of a dataset's files and reports the format each
extension suggests, and whether that format is open, so that a person can see which files may
need converting before deposit. It never converts, renames or deletes a file.

The mock looks each file's last extension up in `formats.yaml`. It reads no file, consults no
source and calls no model, so its grounding mode is `none` and it cites only its input. The real
archivist, which identifies formats from content with PRONOM (fido), describes tables with
Frictionless and records digests (#198, #13), is TODO(#354).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import yaml

from dd_agent_advisor_files.classes import FileEntry, FileInventory, FileList, InventoryEntry
from dd_sdk import serve
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    EvidenceItem,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION

FORMATS = Path(__file__).with_name("formats.yaml")
UNKNOWN = "unknown"

LIMITATIONS = (
    "This is a mock: it reads no file and guesses each format from the file name's extension only.",
    "An extension can be wrong or missing; it does not identify formats from content (PRONOM).",
    "It does not check that files open, describe tables, record checksums or suggest conversions.",
)


@dataclass(frozen=True)
class Format:
    name: str
    media_type: str
    open: bool


def load_formats(path: Path = FORMATS) -> dict[str, Format]:
    with path.open(encoding="utf-8") as fh:
        table = yaml.safe_load(fh)
    return {
        str(ext).lower(): Format(str(row["format"]), str(row["media_type"]), bool(row["open"]))
        for ext, row in table.items()
    }


class FileArchivist:
    spec = AgentSpec(
        agent_id="advisor.files",
        version="0.1.0a1",
        title="File Archivist",
        description=(
            "Mock. Lists a dataset's files with the format each file name's extension suggests, "
            "and whether that format is open. Reads no file and identifies nothing from content."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(FileList),),
        grounding_mode=GroundingMode.NONE,
        payload=ClassSchema.of(FileInventory),
        derivations={
            "entries.extension": Derived(Derivation.LEXICAL),
            "entries.format_name": Derived(Derivation.LEXICAL),
            "entries.media_type": Derived(Derivation.LEXICAL),
            "entries.open_format": Derived(Derivation.LEXICAL),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("preparation.files",),
    )

    def __init__(self, formats: dict[str, Format] | None = None) -> None:
        self.formats = formats if formats is not None else load_formats()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        listing = request.input
        assert isinstance(listing, FileList)  # the conductor checked spec.accepts
        if not listing.files:
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.INSUFFICIENT_INPUT,
                    statement="List the dataset's files, by name, to have their formats reported.",
                )
            )

        entries = [self._entry(file) for file in listing.files]
        closed = sum(not e.open_format for e in entries)
        ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"Mock: {closed} of {len(entries)} files have an extension that suggests a "
                    "format that is not open, or that is unknown. A person must check each file."
                ),
            ),
            payload=FileInventory(
                entries=entries,
                limitations=list(LIMITATIONS),
                grounded_on=[ref],
            ),
            evidence=[
                EvidenceItem(
                    source_id=ctx.input_ref,
                    retrieved_at=datetime.now(UTC),
                    hash_algorithm=HASH_ALGORITHM,
                    canonicalisation=INPUT_CANONICALISATION,
                    content_hash=ctx.input_hash,
                )
            ],
        )

    def _entry(self, file: FileEntry) -> InventoryEntry:
        extension = PurePosixPath(file.name.replace("\\", "/")).suffix.lstrip(".").lower()
        known = self.formats.get(extension)
        if known is None:
            return InventoryEntry(
                name=file.name, extension=extension, format_name=UNKNOWN, open_format=False
            )
        return InventoryEntry(
            name=file.name,
            extension=extension,
            format_name=known.name,
            media_type=known.media_type,
            open_format=known.open,
        )


def build() -> FileArchivist:
    return FileArchivist()


def main() -> int:
    """The `dd-advisor-files` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)

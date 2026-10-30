"""advisor.files: the File Archivist persona (ADR-0033). A mock.

Serves `preparation.files`. It takes a project's file inventory (ADR-0034) and reports the format
each file is judged to be, and whether that format is open, so that a person can see which files
may need converting before deposit. It never converts, renames or deletes a file.

The mock looks up the media type the inventory gives, which `dd-inventory` may have read from the
file's content with fido, in `formats.yaml`; failing that, the file's last extension. It reads no
file, consults no source and calls no model, so its grounding mode is `none` and it cites only
its input. The real archivist, which weighs the inventory's PRONOM identifiers and table fields,
is TODO(#354).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import yaml

from dd_agent_advisor_files.classes import FileAssessment, FormatAssessment, JudgedBy
from dd_sdk import serve
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    EvidenceItem,
    FileInventory,
    GroundingMode,
    GroundingRef,
    InventoryFile,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION

FORMATS = Path(__file__).with_name("formats.yaml")
UNKNOWN = "unknown"
# Says nothing about a format, so it is never looked up.
OCTET_STREAM = "application/octet-stream"

LIMITATIONS = (
    "This is a mock: it judges each format from the inventory's media type or, failing that, the "
    "file name's extension, using a short table.",
    "It does not weigh the inventory's PRONOM identifiers or table fields.",
    "It does not check that files open or suggest conversions.",
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
            "Mock. Lists each file of a project's inventory with the format its media type or "
            "extension suggests, and whether that format is open. Reads no file."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(FileInventory),),
        grounding_mode=GroundingMode.NONE,
        payload=ClassSchema.of(FormatAssessment),
        derivations={
            "assessments.extension": Derived(Derivation.LEXICAL),
            "assessments.format_name": Derived(Derivation.LEXICAL),
            "assessments.media_type": Derived(Derivation.LEXICAL),
            "assessments.open_format": Derived(Derivation.LEXICAL),
            "assessments.judged_by": Derived(Derivation.LEXICAL),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("preparation.files",),
    )

    def __init__(self, formats: dict[str, Format] | None = None) -> None:
        self.formats = formats if formats is not None else load_formats()
        self.by_media_type: dict[str, Format] = {}
        for known in self.formats.values():
            if known.media_type != OCTET_STREAM:
                self.by_media_type.setdefault(known.media_type, known)

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        inventory = request.input
        assert isinstance(inventory, FileInventory)  # the conductor checked spec.accepts
        if not inventory.inventory_files:
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.INSUFFICIENT_INPUT,
                    statement=(
                        "The inventory lists no files. Run dd-inventory on the dataset's folder "
                        "and add the inventory to the project."
                    ),
                )
            )

        assessments = [self._assess(file) for file in inventory.inventory_files]
        closed = sum(not a.open_format for a in assessments)
        ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"Mock: {closed} of {len(assessments)} files are in a format that is not "
                    "open, or that is unknown. A person must check each file."
                ),
            ),
            payload=FormatAssessment(
                assessments=assessments,
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

    def _assess(self, file: InventoryFile) -> FileAssessment:
        extension = PurePosixPath(file.file_path).suffix.lstrip(".").lower()
        known = self.by_media_type.get(file.file_media_type or "")
        judged_by = JudgedBy.MEDIA_TYPE
        if known is None:
            known, judged_by = self.formats.get(extension), JudgedBy.EXTENSION
        if known is None:
            return FileAssessment(
                path=file.file_path,
                extension=extension,
                format_name=UNKNOWN,
                media_type=file.file_media_type,
                open_format=False,
                judged_by=JudgedBy.NOTHING,
            )
        return FileAssessment(
            path=file.file_path,
            extension=extension,
            format_name=known.name,
            media_type=file.file_media_type or known.media_type,
            open_format=known.open,
            judged_by=judged_by,
        )


def build() -> FileArchivist:
    return FileArchivist()


def main() -> int:
    """The `dd-advisor-files` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)

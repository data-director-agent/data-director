"""advisor.files: the File Archivist persona (docs/specs/agents.md). A model-backed alpha.

Serves `preparation.files`. It takes a project's file inventory (docs/specs/projects.md) and reports
the format each file is judged to be, and whether that format is open, so that a person can see
which files may need converting before deposit. It never converts, renames or deletes a file.

It also lists the files a person should look at before deposit (#449): those whose folder, file or
field names suggest free text, coordinates, someone else's material or terms, operating-system
files, empty files and byte-for-byte copies, by the rules in `dd_sdk.inventory_hints`, which the
harness's deposit check reads too. The inventory holds no
contents, so each is a prompt for a person, never a finding, and a file it does not list may still
hold personal data (docs/specs/personal-data.md).

It describes each file's format from the PRONOM record (`dd_formats`, a pinned PRONOM release)
of the first PRONOM identifier the inventory gives that the release has; `dd-inventory` read those
identifiers from the file's content with fido. Each such assessment cites its record (grounding mode
`retrieval`, #955). Whether a format is open is the agent's own judgement, from `formats.yaml`,
since PRONOM does not say. Failing a PRONOM record, it judges by the media type the inventory gives,
then the file's last extension, from the same table, and cites only its input. An identifier the
release does not have is reported as identified but not described, and a known extension that the
record does not list is a check for a person.
It reads no file and sends nothing anywhere. Each format and check is decided by rule; a
summariser (`dd_sdk.summary`) then writes a short summary beside them: a model's by default, the
rules' own with `DD_FILES_SUMMARISER=template` (`factory.py`). The real archivist, which also weighs
table fields, is TODO(#354).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import yaml

import dd_formats
from dd_agent_advisor_files.classes import (
    CheckKind,
    FileAssessment,
    FileCheck,
    FormatAssessment,
    JudgedBy,
)
from dd_sdk import inventory_hints, summary
from dd_sdk.agent import (
    AgentResult,
    AgentSpec,
    Derived,
    RunContext,
    abstain,
    input_evidence,
    input_ref,
)
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
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, HASH_ALGORITHM, content_hash, project
from dd_sdk.inventory_hints import RULES, Rule
from dd_sdk.tracing import retrieval_span

FORMATS = Path(__file__).with_name("formats.yaml")
UNKNOWN = "unknown"
# Says nothing about a format, so it is never looked up.
OCTET_STREAM = "application/octet-stream"
MISMATCH_QUESTION = (
    "The file's content was identified as one format but its name suggests another. Check that "
    "it is the file it is meant to be, and rename it or replace it if not."
)

LIMITATIONS = (
    "It describes each format from the PRONOM record of an identifier the inventory gives, from "
    "a pinned PRONOM release; failing one, from the inventory's media type or the file name's "
    "extension, using a short table of formats.",
    "Whether a format is open is the agent's own judgement from a short table, not PRONOM's: a "
    "format outside it is described but not judged open or not.",
    "It does not weigh the inventory's table fields.",
    "It does not check that files open or suggest conversions.",
    "It reads folder, file and field names, never contents: a file it does not list for a person "
    "to look at may still hold personal data, sensitive locations or someone else's material.",
    "Its summary is written by a model from the findings alone unless the template is chosen; "
    "the findings above it are the agent's judgement, not the summary.",
)


@dataclass(frozen=True)
class Format:
    """A format the table describes for a file with no PRONOM record."""

    name: str
    media_type: str
    open: bool


@dataclass(frozen=True)
class Formats:
    """`formats.yaml`: whether each PRONOM-identified format is open, and the formats that file
    extensions suggest."""

    open: dict[str, bool]
    extensions: dict[str, Format]


def load_formats(path: Path = FORMATS) -> Formats:
    with path.open(encoding="utf-8") as fh:
        table = yaml.safe_load(fh)
    return Formats(
        open={str(puid): bool(value) for puid, value in table["open"].items()},
        extensions={
            str(ext).lower(): Format(str(row["format"]), str(row["media_type"]), bool(row["open"]))
            for ext, row in table["extensions"].items()
        },
    )


@dataclass(frozen=True)
class Cited:
    """A PRONOM record as the agent cites it: its reference and its evidence content."""

    ref: GroundingRef
    content: dict[str, object]
    url: str


def _cite(record: dd_formats.FormatRecord) -> Cited:
    content = project(record.as_dict(), DOCUMENT_CANONICALISATION)
    digest = content_hash(content, DOCUMENT_CANONICALISATION)
    return Cited(GroundingRef(source_id=record.puid, content_hash=digest), content, record.url)


def _display_name(record: dd_formats.FormatRecord) -> str:
    """PRONOM's name, with its version where the name does not already end with it."""
    if record.version and not record.name.endswith(record.version):
        return f"{record.name} {record.version}"
    return record.name


class FileArchivist:
    spec = AgentSpec(
        agent_id="advisor.files",
        version="0.3.0a1",
        title="File Archivist",
        icon="🗄️",
        description=(
            "Lists each file of a project's inventory with its format, described from the PRONOM "
            "record of its identification, or else suggested by its media type or extension, and "
            "whether that format is open, "
            "and the files whose names, size or digest call for a person to look at them "
            "before deposit, with a short summary. Reads no file."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(FileInventory),),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload=ClassSchema.of(FormatAssessment),
        derivations={
            "assessments.extension": Derived(Derivation.LEXICAL),
            "assessments.format_name": Derived(Derivation.LEXICAL),
            "assessments.media_type": Derived(Derivation.LEXICAL),
            "assessments.open_format": Derived(Derivation.LEXICAL),
            "assessments.judged_by": Derived(Derivation.LEXICAL),
            "assessments.pronom_id": Derived(Derivation.LEXICAL),
            "checks.path": Derived(Derivation.LEXICAL),
            "checks.kind": Derived(Derivation.LEXICAL),
            "checks.matched": Derived(Derivation.LEXICAL),
            "checks.question": Derived(Derivation.TEMPLATE),
            "checks.related_paths": Derived(Derivation.LEXICAL),
            "summary": Derived(Derivation.MODEL, recorded_in="summary_derivation"),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("preparation.files",),
    )

    def __init__(
        self,
        formats: Formats | None = None,
        hints: tuple[Rule, ...] = RULES,
        summariser: summary.Summariser | None = None,
    ) -> None:
        self.formats = formats if formats is not None else load_formats()
        self.hints = hints
        self.summariser = summariser or summary.TemplateSummariser()
        self.by_media_type: dict[str, Format] = {}
        for known in self.formats.extensions.values():
            if known.media_type != OCTET_STREAM:
                self.by_media_type.setdefault(known.media_type, known)

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        inventory = request.input
        assert isinstance(inventory, FileInventory)  # the conductor checked spec.accepts
        if not inventory.inventory_files:
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                (
                    "The inventory lists no files. Run dd-inventory on the dataset's folder "
                    "and add the inventory to the project."
                ),
            )

        assessments = [self._assess(file) for file in inventory.inventory_files]
        cited = self._retrieve(assessments, ctx)
        checks = self._checks(inventory.inventory_files)
        closed = sum(a.open_format is not True for a in assessments)
        statement = _statement(checks, closed, len(assessments))
        told = summary.Findings(
            {
                "assessments": [a.model_dump(mode="json", exclude_none=True) for a in assessments],
                "checks": [c.model_dump(mode="json", exclude_none=True) for c in checks],
            },
            statement,
        )
        summarised, explanation = summary.summarise(self.summariser, told, ctx)
        result = AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
            payload=FormatAssessment(
                assessments=assessments,
                checks=checks,
                summary=summarised.text,
                summary_derivation=summarised.derivation,
                limitations=list(LIMITATIONS),
                grounded_on=[input_ref(ctx), *(c.ref for c in cited)],
            ),
            evidence=[input_evidence(ctx), *(self._evidence(c) for c in cited)],
        )
        return summary.with_calls(result, self.summariser.model_id, explanation)

    def _retrieve(self, assessments: list[FileAssessment], ctx: RunContext) -> list[Cited]:
        """One retrieval span for the input, which every assessment rests on, and one per distinct
        PRONOM record cited, before any model call (docs/specs/grounding.md, G1-G2)."""
        with retrieval_span(ctx.tracer, ctx.input_ref, ctx.input_hash):
            pass
        cited: dict[str, Cited] = {}
        for assessment in assessments:
            if assessment.judged_by != JudgedBy.PRONOM or assessment.pronom_id is None:
                continue
            record = dd_formats.lookup(assessment.pronom_id)
            if record is None or record.puid in cited:
                continue
            cited[record.puid] = _cite(record)
            with retrieval_span(ctx.tracer, record.puid, cited[record.puid].ref.content_hash):
                pass
        return list(cited.values())

    @staticmethod
    def _evidence(cited: Cited) -> EvidenceItem:
        return EvidenceItem(
            source_id=cited.ref.source_id,
            source_uri=cited.url,
            retrieved_at=datetime.now(UTC),
            snapshot_ref=snapshot_ref(),
            hash_algorithm=HASH_ALGORITHM,
            canonicalisation=DOCUMENT_CANONICALISATION,
            content_hash=cited.ref.content_hash,
            content=cited.content,
        )

    def _checks(self, files: list[InventoryFile]) -> list[FileCheck]:
        by_path: dict[str, list[FileCheck]] = defaultdict(list)
        for hint in inventory_hints.hints(files, self.hints):
            by_path[hint.path].append(
                FileCheck(
                    path=hint.path,
                    kind=CheckKind(hint.kind.value),
                    matched=hint.matched,
                    question=hint.question,
                    related_paths=list(hint.related_paths),
                )
            )
        checks = []
        for file in files:
            checks += by_path.get(file.file_path, [])
            mismatch = self._mismatch(self._assess(file))
            if mismatch is not None:
                checks.append(mismatch)
        return checks

    def _mismatch(self, file: FileAssessment) -> FileCheck | None:
        """The file's PRONOM record does not list an extension the table knows: content-based
        identification and the name suggest different formats. An extension the table does not
        know, or a record that lists none, says nothing either way."""
        if file.judged_by != JudgedBy.PRONOM or file.pronom_id is None:
            return None
        record = dd_formats.lookup(file.pronom_id)
        if file.extension not in self.formats.extensions or record is None:
            return None
        if not record.extensions or file.extension in record.extensions:
            return None
        return FileCheck(
            path=file.path,
            kind=CheckKind.EXTENSION_MISMATCH,
            matched=file.extension,
            question=MISMATCH_QUESTION,
        )

    def _assess(self, file: InventoryFile) -> FileAssessment:
        extension = PurePosixPath(file.file_path).suffix.lstrip(".").lower()
        record = next(
            (r for p in file.file_pronom_ids if (r := dd_formats.lookup(p)) is not None), None
        )
        if record is not None:
            return FileAssessment(
                path=file.file_path,
                extension=extension,
                format_name=_display_name(record),
                media_type=file.file_media_type or next(iter(record.media_types), None),
                open_format=self.formats.open.get(record.puid),
                judged_by=JudgedBy.PRONOM,
                pronom_id=record.puid,
                grounded_on=[_cite(record).ref],
            )
        if file.file_pronom_ids:
            return FileAssessment(
                path=file.file_path,
                extension=extension,
                format_name=UNKNOWN,
                media_type=file.file_media_type,
                judged_by=JudgedBy.PRONOM_UNLISTED,
                pronom_id=file.file_pronom_ids[0],
            )
        known = self.by_media_type.get(file.file_media_type or "")
        judged_by = JudgedBy.MEDIA_TYPE
        if known is None:
            known, judged_by = self.formats.extensions.get(extension), JudgedBy.EXTENSION
        if known is None:
            return FileAssessment(
                path=file.file_path,
                extension=extension,
                format_name=UNKNOWN,
                media_type=file.file_media_type,
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


def snapshot_ref() -> str:
    """The label of the pinned PRONOM release, which a deployment's source check pins a copy of
    (app/config/sources.yaml)."""
    return f"pronom:v{dd_formats.release().version}"


def _statement(checks: list[FileCheck], closed: int, total: int) -> str:
    formats = (
        f"{closed} of {total} files are in a format that is not open, or that is unknown. "
        "A person must check each file."
    )
    if not checks:
        return (
            f"{formats} No folder, file or field name called for a closer look, but the contents "
            "were not read: that does not mean the files hold no personal data, sensitive "
            "locations or someone else's material."
        )
    looked_at = len({c.path for c in checks})
    kinds = ", ".join(dict.fromkeys(c.kind.value.replace("_", " ") for c in checks))
    return (
        f"Before deposit, a person should look at {looked_at} of {total} files ({kinds}): each "
        f"is a prompt, judged from names alone, not a finding. {formats} Contents were not read, "
        "so a file not listed may still need checking."
    )

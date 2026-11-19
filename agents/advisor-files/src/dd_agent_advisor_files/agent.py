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

It looks up the PRONOM identifiers the inventory gives, which `dd-inventory` read from the
file's content with fido, in `formats.yaml`; failing that, the media type the inventory gives;
failing that, the file's last extension. An identifier the table does not know is reported as
identified but not in the table, and an identification that disagrees with the extension is a check
for a person.
It reads no file and consults no source, so it cites only its input (grounding mode
`input_only`). Each format and check is decided by rule; a summariser (`dd_sdk.summary`) then
writes a short summary beside them: a model's by default, the rules' own with
`DD_FILES_SUMMARISER=template` (`factory.py`). The real archivist, which also weighs table fields,
is TODO(#354).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

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
    FileInventory,
    GroundingMode,
    InventoryFile,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)
from dd_sdk.inventory_hints import RULES, Rule

FORMATS = Path(__file__).with_name("formats.yaml")
UNKNOWN = "unknown"
# Says nothing about a format, so it is never looked up.
OCTET_STREAM = "application/octet-stream"
MISMATCH_QUESTION = (
    "The file's content was identified as one format but its name suggests another. Check that "
    "it is the file it is meant to be, and rename it or replace it if not."
)

LIMITATIONS = (
    "It judges each format by the inventory's PRONOM identifiers, its media type "
    "or the file name's extension, using a short table of formats.",
    "A format outside that table is reported as such, not described.",
    "It does not weigh the inventory's table fields.",
    "It does not check that files open or suggest conversions.",
    "It reads folder, file and field names, never contents: a file it does not list for a person "
    "to look at may still hold personal data, sensitive locations or someone else's material.",
    "Its summary is written by a model from the findings alone unless the template is chosen; "
    "the findings above it are the agent's judgement, not the summary.",
)


@dataclass(frozen=True)
class Format:
    name: str
    media_type: str
    open: bool
    pronom: tuple[str, ...] = ()


def load_formats(path: Path = FORMATS) -> dict[str, Format]:
    with path.open(encoding="utf-8") as fh:
        table = yaml.safe_load(fh)
    return {
        str(ext).lower(): Format(
            str(row["format"]),
            str(row["media_type"]),
            bool(row["open"]),
            tuple(str(p) for p in row.get("pronom", ())),
        )
        for ext, row in table.items()
    }


class FileArchivist:
    spec = AgentSpec(
        agent_id="advisor.files",
        version="0.2.0a1",
        title="File Archivist",
        icon="🗄️",
        description=(
            "Lists each file of a project's inventory with the format its PRONOM "
            "identification, media type or extension suggests, and whether that format is open, "
            "and the files whose names, size or digest call for a person to look at them "
            "before deposit, with a short summary. Reads no file."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(FileInventory),),
        grounding_mode=GroundingMode.INPUT_ONLY,
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
        formats: dict[str, Format] | None = None,
        hints: tuple[Rule, ...] = RULES,
        summariser: summary.Summariser | None = None,
    ) -> None:
        self.formats = formats if formats is not None else load_formats()
        self.hints = hints
        self.summariser = summariser or summary.TemplateSummariser()
        self.by_media_type: dict[str, Format] = {}
        self.by_puid: dict[str, Format] = {}
        for known in self.formats.values():
            for puid in known.pronom:
                self.by_puid.setdefault(puid, known)
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
        checks = self._checks(inventory.inventory_files)
        closed = sum(not a.open_format for a in assessments)
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
                grounded_on=[input_ref(ctx)],
            ),
            evidence=[input_evidence(ctx)],
        )
        return summary.with_calls(result, self.summariser.model_id, explanation)

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
        """Content-based identification and the extension name different formats."""
        by_extension = self.formats.get(file.extension)
        if file.judged_by != JudgedBy.PRONOM or by_extension is None:
            return None
        if by_extension.name == file.format_name:
            return None
        return FileCheck(
            path=file.path,
            kind=CheckKind.EXTENSION_MISMATCH,
            matched=file.extension,
            question=MISMATCH_QUESTION,
        )

    def _assess(self, file: InventoryFile) -> FileAssessment:
        extension = PurePosixPath(file.file_path).suffix.lstrip(".").lower()
        puid = next((p for p in file.file_pronom_ids if p in self.by_puid), None)
        if puid is None and file.file_pronom_ids:
            return FileAssessment(
                path=file.file_path,
                extension=extension,
                format_name=UNKNOWN,
                media_type=file.file_media_type,
                open_format=False,
                judged_by=JudgedBy.PRONOM_UNLISTED,
                pronom_id=file.file_pronom_ids[0],
            )
        known = self.by_puid[puid] if puid else self.by_media_type.get(file.file_media_type or "")
        judged_by = JudgedBy.PRONOM if puid else JudgedBy.MEDIA_TYPE
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
            pronom_id=puid,
        )


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

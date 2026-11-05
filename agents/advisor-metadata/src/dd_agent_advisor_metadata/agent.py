"""advisor.metadata: the Metadata Librarian persona (docs/specs/agents.md). A mock, and the
stub drafter of the project's metadata record (#200).

Serves `preparation.metadata-standard` and `preparation.metadata` (R2). Given a `DraftRequest` for
a `metadata_record`, it drafts a project document (docs/specs/projects.md): a DataCite record in
DataCite's JSON form, with `conforms_to` set to the chosen repository's (docs/specs/deposit.md).
Every property the repository's requirements list is written, with its qualifier, and its value
left null for the researcher. The mock fills only what holds for any deposit, that the resource
is a dataset, and what the inventory states: the files' formats and sizes.

It reads the DataCite JSON form from `datacite.yaml`. It consults no source, uses no controlled
vocabulary, maps nothing between schemas (R6) and calls no model, so its grounding mode is `none`
and it cites only its input. Regenerating a record drafts it afresh, and names the version it
replaces in `revises`. The real librarian is TODO(#357).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from dd_sdk import serve
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    Document,
    DocumentKind,
    DraftRequest,
    EvidenceItem,
    FileInventory,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Obligation,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    RepositoryRequirements,
)
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION

DATACITE_FORM = Path(__file__).with_name("datacite.yaml")
# The schema every record follows in the MVP (docs/specs/deposit.md).
DATACITE = "http://datacite.org/schema/kernel-4"
MEDIA_TYPE = "application/json"

# What the mock does not do, said in every outcome: its payload is the core Document, which has
# no room for a list of limitations (docs/specs/agents.md).
LIMITATIONS = (
    "This is a mock: it writes the properties the repository asks for and fills none that only "
    "you can, uses no controlled vocabularies, maps nothing between schemas, and reads neither an "
    "earlier version nor the reason given for a decision on it."
)


@dataclass(frozen=True, slots=True)
class Form:
    """How one DataCite property is written: the key of its value in a list entry, or a value
    the mock fills itself."""

    value: str | None = None
    filled: str | None = None


def load_form(path: Path = DATACITE_FORM) -> dict[str, Form]:
    with path.open(encoding="utf-8") as fh:
        table = yaml.safe_load(fh)
    form = {}
    for prop, entry in table.items():
        unknown = set(entry) - {"value", "filled"}
        if unknown or len(entry) != 1:
            raise ValueError(f"{path}: {prop} needs exactly one of value or filled")
        form[str(prop)] = Form(**entry)
    return form


class MetadataLibrarian:
    spec = AgentSpec(
        agent_id="advisor.metadata",
        version="0.1.0a1",
        title="Metadata Librarian",
        description=(
            "Mock. Drafts a project's metadata record in DataCite's JSON form, with every property "
            "the chosen repository requires or recommends, filling only the resource type and the "
            "formats and sizes the file inventory gives. The researcher writes the rest."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(DraftRequest),),
        grounding_mode=GroundingMode.NONE,
        payload=ClassSchema.of(Document),
        derivations={
            "document_title": Derived(Derivation.TEMPLATE),
            "document_text": Derived(Derivation.TEMPLATE),
        },
        serves=("preparation.metadata-standard", "preparation.metadata"),
    )

    def __init__(self, form: dict[str, Form] | None = None) -> None:
        self.form = form if form is not None else load_form()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        asked = request.input
        assert isinstance(asked, DraftRequest)  # the conductor checked spec.accepts
        if asked.document_kind != DocumentKind.METADATA_RECORD:
            return _abstain(
                ReasonCode.OUTSIDE_AGENT_SCOPE,
                "The Metadata Librarian drafts a metadata record, not a "
                f"{asked.document_kind.value}.",
            )
        requirements = asked.requirements
        if requirements is None:
            return _abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "Choose a repository first: the record has the properties it asks for.",
            )
        if requirements.conforms_to != DATACITE:
            return _abstain(
                ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
                f"The mock drafts DataCite records only, not {requirements.conforms_to}.",
            )

        record, filled = self._record(requirements, asked.inventory)
        required = sum(f.obligation == Obligation.REQUIRED for f in requirements.fields)
        statement = (
            f"Mock: a DataCite record for {requirements.repository_name} with the "
            f"{len(requirements.fields)} properties it asks for ({required} required). Filled: "
            f"{', '.join(filled) or 'nothing'}. Every null value is for you to write."
        )
        current = asked.current_version
        if current is not None:
            statement += f" It replaces version {current.version_ref.version} of the document."

        ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=f"{statement} {LIMITATIONS}"),
            payload=Document(
                document_kind=DocumentKind.METADATA_RECORD,
                document_title=(current.document_title if current else None)
                or f"Metadata record for {requirements.repository_name}",
                media_type=MEDIA_TYPE,
                conforms_to=requirements.conforms_to,
                document_text=json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                document_derivation=Derivation.TEMPLATE,
                revises=current.version_ref if current else None,
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

    def _record(
        self, requirements: RepositoryRequirements, inventory: FileInventory | None
    ) -> tuple[dict[str, Any], list[str]]:
        """The record, and the properties the mock filled."""
        record: dict[str, Any] = {}
        filled: list[str] = []
        for field in requirements.fields:
            form = self.form.get(field.property, Form())
            *parents, last = field.property.split(".")
            node = record
            for part in parents:
                node = node.setdefault(part, {})
            if form.filled is not None:
                node[last] = form.filled
                filled.append(field.property)
            elif form.value is not None:
                entry = {form.value: None, **(field.qualifier or {})}
                node.setdefault(last, []).append(entry)
            else:
                node.setdefault(last, None)
        if inventory is not None and inventory.inventory_files:
            files = inventory.inventory_files
            record["formats"] = sorted({f.file_media_type for f in files if f.file_media_type})
            total = sum(f.file_size for f in files)
            record["sizes"] = [f"{len(files)} files", f"{total} bytes"]
            filled += ["formats", "sizes"] if record["formats"] else ["sizes"]
            if not record["formats"]:
                del record["formats"]
        record["schemaVersion"] = requirements.conforms_to
        return record, filled


def _abstain(reason: ReasonCode, statement: str) -> AgentResult:
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.ABSTAINED, reason_code=reason, statement=statement)
    )


def build() -> MetadataLibrarian:
    return MetadataLibrarian()


def main() -> int:
    """The `dd-advisor-metadata` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)

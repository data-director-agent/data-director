"""advisor.metadata: the Metadata Librarian persona (ADR-0033). A mock.

Serves `preparation.metadata-standard` and `preparation.metadata`. It picks a metadata standard,
the one the researcher asked for if it knows it and DataCite otherwise, and drafts a record in it
for the researcher to review before submission (R2). It copies what the researcher gave into the
standard's properties and never invents a value: a property the input cannot fill is left empty
and marked for the researcher.

The mock reads its standards from `standards.yaml`. It consults no source, uses no controlled
vocabulary, maps nothing between schemas (R6) and calls no model, so its grounding mode is `none`
and it cites only its input. The real librarian is TODO(#357).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from dd_agent_advisor_metadata.classes import DraftField, MetadataDraft, MetadataDraftRequest
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

STANDARDS = Path(__file__).with_name("standards.yaml")
IGNORED = re.compile(r"[\s_-]+")
# The input fields a property may be filled from: the slots of MetadataDraftRequest that hold a
# description of the dataset.
SOURCES = frozenset({"title", "description", "creators", "keywords", "publication_year"})
# How a list from the input (creators, keywords) is written as one property value.
SEPARATOR = "; "

FILLED = "filled"
NEEDS_RESEARCHER = "needs_researcher"

LIMITATIONS = (
    "This is a mock: it copies your input into a fixed list of properties and checks nothing.",
    "It knows only a few properties of DataCite, Dublin Core and DDI-Codebook, not whole schemas.",
    "It does not choose a standard for your discipline; it uses the one you name, or DataCite.",
    "It uses no controlled vocabularies and does not split names into given and family names.",
    "It does not map a record from one schema to another.",
    "Properties marked needs_researcher are left empty for you to fill, not found to be unknown.",
)


@dataclass(frozen=True, slots=True)
class Standard:
    name: str
    aliases: frozenset[str]
    properties: tuple[tuple[str, str | None], ...]


def normalise(name: str) -> str:
    return IGNORED.sub(" ", name.strip().lower())


def load_standards(path: Path = STANDARDS) -> tuple[Standard, ...]:
    with path.open(encoding="utf-8") as fh:
        table = yaml.safe_load(fh)
    standards = []
    for name, entry in table.items():
        properties = tuple((str(p["name"]), p["from"]) for p in entry["properties"])
        unknown = {source for _, source in properties if source is not None} - SOURCES
        if unknown:
            raise ValueError(f"{path}: {name} fills from unknown input fields {sorted(unknown)}")
        aliases = frozenset(normalise(a) for a in [name, *entry.get("aliases", [])])
        standards.append(Standard(str(name), aliases, properties))
    if not standards:
        raise ValueError(f"{path}: no standards")
    return tuple(standards)


class MetadataLibrarian:
    spec = AgentSpec(
        agent_id="advisor.metadata",
        version="0.1.0a1",
        title="Metadata Librarian",
        description=(
            "Mock. Drafts a metadata record in DataCite, Dublin Core or DDI-Codebook from what the "
            "researcher gives, and marks every property it cannot fill for the researcher. Never "
            "invents a value, and the researcher reviews the draft before submission."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(MetadataDraftRequest),),
        grounding_mode=GroundingMode.NONE,
        payload=ClassSchema.of(MetadataDraft),
        derivations={
            "standard": Derived(Derivation.TEMPLATE),
            "standard_reason": Derived(Derivation.TEMPLATE),
            "fields.name": Derived(Derivation.TEMPLATE),
            "fields.value": Derived(Derivation.LEXICAL),
            "fields.status": Derived(Derivation.TEMPLATE),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("preparation.metadata-standard", "preparation.metadata"),
    )

    def __init__(self, standards: tuple[Standard, ...] | None = None) -> None:
        self.standards = standards if standards is not None else load_standards()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        draft = request.input
        assert isinstance(draft, MetadataDraftRequest)  # the conductor checked spec.accepts
        if not (draft.title and draft.title.strip()):
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.INSUFFICIENT_INPUT,
                    statement="Give the dataset's title: every standard the mock drafts needs one.",
                )
            )

        standard, reason = self._choose(draft.target_standard)
        fields = [self._field(draft, name, source) for name, source in standard.properties]
        filled = sum(f.status == FILLED for f in fields)

        ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"Mock: a {standard.name} draft with {filled} of {len(fields)} properties "
                    "filled from your input. You must supply the rest and review every value "
                    "before submission."
                ),
            ),
            payload=MetadataDraft(
                standard=standard.name,
                standard_reason=reason,
                fields=fields,
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

    def _choose(self, requested: str | None) -> tuple[Standard, str]:
        default = self.standards[0]
        if not (requested and requested.strip()):
            return (
                default,
                f"No standard was requested, so the mock uses its default, {default.name}.",
            )
        wanted = normalise(requested)
        for standard in self.standards:
            if wanted in standard.aliases:
                return standard, f"Requested: {requested.strip()}."
        return default, (
            f"The mock does not know the requested standard, {requested.strip()!r}, so it uses its "
            f"default, {default.name}. Check with your repository which standard it expects."
        )

    @staticmethod
    def _field(draft: MetadataDraftRequest, name: str, source: str | None) -> DraftField:
        value = None if source is None else getattr(draft, source)
        if isinstance(value, list):
            value = SEPARATOR.join(v.strip() for v in value if v.strip()) or None
        elif isinstance(value, str):
            value = value.strip() or None
        elif value is not None:
            value = str(value)
        if value is None:
            return DraftField(name=name, status=NEEDS_RESEARCHER)
        return DraftField(name=name, value=value, status=FILLED)


def build() -> MetadataLibrarian:
    return MetadataLibrarian()


def main() -> int:
    """The `dd-advisor-metadata` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)

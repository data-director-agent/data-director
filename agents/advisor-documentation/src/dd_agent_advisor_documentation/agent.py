"""advisor.documentation: the Documentation Editor persona (ADR-0033). A mock.

Serves `setup.documentation` and `preparation.documentation` (R5). It drafts a README outline and a
data dictionary from what the researcher gave: what can be inferred from the input, such as the
file names and field names, is drafted; what cannot, such as variable definitions, units, missing
value codes and the study design, is marked for the researcher.

The mock fills README sections by copying its input, as `readme.yaml` lays out, and writes no prose
of its own. It reads no files, consults no source and calls no model, so its grounding mode is
`none` and it cites only its input. The real editor is TODO(#358).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import yaml

from dd_agent_advisor_documentation.classes import (
    DictionaryEntry,
    DocumentationDraft,
    DocumentationRequest,
    DraftStatus,
    ReadmeSection,
)
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

README = Path(__file__).with_name("readme.yaml")
# The DocumentationRequest slots a README section may be drafted from.
SOURCES = frozenset({"title", "description", "creators", "files", "fields"})

LIMITATIONS = (
    "This is a mock: it drafts README sections only by copying what you gave, and writes no prose "
    "of its own.",
    "It does not open the files, so it says nothing about their contents, formats or sizes.",
    "It infers no variable definitions, units or missing value codes: every data dictionary entry "
    "is left for you.",
    "Methods, licence and how to cite are left for you.",
    "It follows no community README template or data dictionary standard.",
)


class Rule(NamedTuple):
    heading: str
    source: str | None  # the DocumentationRequest slot, or None: the researcher writes it


def load_rules(path: Path = README) -> list[Rule]:
    with path.open(encoding="utf-8") as fh:
        table = yaml.safe_load(fh)
    rules = []
    for entry in table:
        source = entry.get("from")
        if source is not None and source not in SOURCES:
            raise ValueError(f"{path}: section {entry['heading']!r} drafts from unknown {source!r}")
        rules.append(Rule(heading=str(entry["heading"]), source=source))
    return rules


class DocumentationEditor:
    spec = AgentSpec(
        agent_id="advisor.documentation",
        version="0.1.0a1",
        title="Documentation Editor",
        description=(
            "Mock. Drafts a README outline and a data dictionary from a dataset's title, creators, "
            "file names and field names, and marks for the researcher everything it cannot "
            "infer: definitions, units, missing value codes, methods, licence and citation."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(DocumentationRequest),),
        grounding_mode=GroundingMode.NONE,
        payload=ClassSchema.of(DocumentationDraft),
        derivations={
            "readme_sections.heading": Derived(Derivation.TEMPLATE),
            "readme_sections.text": Derived(Derivation.TEMPLATE),
            "readme_sections.draft_status": Derived(Derivation.TEMPLATE),
            "dictionary.draft_status": Derived(Derivation.TEMPLATE),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("setup.documentation", "preparation.documentation"),
    )

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self.rules = rules if rules is not None else load_rules()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        context = request.input
        assert isinstance(context, DocumentationRequest)  # the conductor checked spec.accepts
        if not context.files and not context.fields:
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.INSUFFICIENT_INPUT,
                    statement="Give the dataset's file names or field names to draft from.",
                )
            )

        sections = [self._section(rule, context) for rule in self.rules]
        dictionary = [
            DictionaryEntry(field=name, draft_status=DraftStatus.NEEDS_RESEARCHER)
            for name in context.fields
        ]
        drafted = sum(s.draft_status == DraftStatus.DRAFTED for s in sections)

        ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"Mock: {drafted} of {len(sections)} README sections copied from your input. "
                    f"The other sections and all {len(dictionary)} data dictionary entries need "
                    "you to write them."
                ),
            ),
            payload=DocumentationDraft(
                readme_sections=sections,
                dictionary=dictionary,
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

    @staticmethod
    def _section(rule: Rule, context: DocumentationRequest) -> ReadmeSection:
        value = getattr(context, rule.source) if rule.source is not None else None
        if isinstance(value, list):
            value = "\n".join(f"- {item}" for item in value)
        if not value:
            return ReadmeSection(heading=rule.heading, draft_status=DraftStatus.NEEDS_RESEARCHER)
        return ReadmeSection(heading=rule.heading, text=value, draft_status=DraftStatus.DRAFTED)


def build() -> DocumentationEditor:
    return DocumentationEditor()


def main() -> int:
    """The `dd-advisor-documentation` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)

"""advisor.metadata: the Metadata Librarian persona (docs/specs/agents.md), a model-backed alpha,
and the drafter of the project's metadata record (#200, #698).

Serves `preparation.metadata-standard` and `preparation.metadata` (R2). Given a `DraftRequest` for
a `metadata_record`, it drafts a project document (docs/specs/projects.md): a DataCite record in
DataCite's JSON form, with `conforms_to` set to the chosen repository's (docs/specs/deposit.md).
Every property the repository's requirements list is written, with its qualifier, and its value
left null for the researcher. The librarian fills only what holds for any deposit, that the
resource is a dataset, what the inventory states, the files' formats and sizes, and what the
project's researchers kept from their public ORCID records (docs/specs/projects.md): each
researcher as a creator, with their iD and current employers, their keywords as subjects, and
their grants as funding references, wherever the repository asks for those properties.

Each value it leaves null is a gap with a question (`questions.py`), and an answer the researcher
recorded to it is placed as given (docs/specs/drafting.md). Where a model is configured
(`factory.py`), it suggests values for some questions, beside the question and never in the
record (`suggest.py`); the record's text is the rule's either way.

It reads the DataCite JSON form from `datacite.yaml`. It consults no source, uses no controlled
vocabulary and maps nothing between schemas (R6), so its grounding mode is `input_only` and it
cites only its input. Regenerating a record drafts it afresh, and names the version it replaces
in `revises`. Controlled vocabularies and schema mapping are TODO(#703).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from dd_agent_advisor_metadata.questions import (
    Gap,
    answers_by_question,
    ask,
    gaps,
    place,
)
from dd_agent_advisor_metadata.suggest import Ask, Suggester, Suggestions, TemplateSuggester
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
    Document,
    DocumentKind,
    DocumentQuestion,
    DraftRequest,
    FileInventory,
    GroundingMode,
    InvocationRequest,
    Obligation,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    RepositoryRequirements,
)
from dd_sdk.contract.researcher import (
    Affiliation,
    AffiliationKind,
    ResearcherFunding,
    ResearcherRecord,
)

DATACITE_FORM = Path(__file__).with_name("datacite.yaml")
# The schema every record follows in the MVP (docs/specs/deposit.md).
DATACITE = "http://datacite.org/schema/kernel-4"
MEDIA_TYPE = "application/json"

# What the librarian does not do, said in every outcome: its payload is the core Document, which
# has no room for a list of limitations (docs/specs/agents.md).
LIMITATIONS = (
    "It is an alpha: it fills no value that only you can give, beyond what you kept from your "
    "ORCID record and the answers you recorded; it uses no controlled vocabularies, maps nothing "
    "between schemas, does not check that a value is correct, and reads neither an earlier "
    "version nor the reason given for a decision on it."
)
# DataCite's names for the identifier schemes ORCID gives funders in.
FUNDER_SCHEMES = {"FUNDREF": "Crossref Funder ID", "ROR": "ROR", "GRID": "GRID", "ISNI": "ISNI"}
SCHEME_URIS = {"ROR": "https://ror.org", "GRID": "https://www.grid.ac", "ISNI": "https://isni.org"}


@dataclass(frozen=True, slots=True)
class Form:
    """How one DataCite property is written: the key of its value in a list entry, or a value
    the librarian fills itself; the question asked about a value left null, and whether a model
    may suggest one."""

    value: str | None = None
    filled: str | None = None
    ask: str | None = None
    suggest: bool = False


def load_form(path: Path = DATACITE_FORM) -> dict[str, Form]:
    with path.open(encoding="utf-8") as fh:
        table = yaml.safe_load(fh)
    form = {}
    for prop, entry in table.items():
        unknown = set(entry) - {"value", "filled", "ask", "suggest"}
        if unknown:
            raise ValueError(f"{path}: {prop} has unknown keys {sorted(unknown)}")
        if "value" in entry and "filled" in entry:
            raise ValueError(f"{path}: {prop} has a value key or a filled value, not both")
        if "filled" in entry and {"ask", "suggest"} & set(entry):
            raise ValueError(f"{path}: {prop} is filled, so nothing is asked or suggested")
        form[str(prop)] = Form(**entry)
    return form


class MetadataLibrarian:
    spec = AgentSpec(
        agent_id="advisor.metadata",
        version="0.2.0a1",
        title="Metadata Librarian",
        icon="🏷️",
        description=(
            "Alpha. Drafts a project's metadata record in DataCite's JSON form, with every "
            "property the chosen repository requires or recommends, filling only the resource "
            "type, the formats and sizes the file inventory gives, the creators, subjects and "
            "funding the researchers kept from their ORCID records, and the answers they "
            "recorded. It asks about every value it leaves empty, and where a model is "
            "configured suggests some, beside the question and never in the record."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(DraftRequest),),
        grounding_mode=GroundingMode.INPUT_ONLY,
        payload=ClassSchema.of(Document),
        derivations={
            "document_title": Derived(Derivation.TEMPLATE),
            "document_text": Derived(Derivation.TEMPLATE),
            "document_questions": Derived(Derivation.TEMPLATE),
            "document_questions.suggested_answer": Derived(
                Derivation.MODEL, recorded_in="suggestion_derivation"
            ),
        },
        serves=("preparation.metadata-standard", "preparation.metadata"),
    )

    def __init__(
        self, form: dict[str, Form] | None = None, suggester: Suggester | None = None
    ) -> None:
        self.form = form if form is not None else load_form()
        self.suggester = suggester if suggester is not None else TemplateSuggester()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        asked = request.input
        assert isinstance(asked, DraftRequest)  # the conductor checked spec.accepts
        if asked.document_kind != DocumentKind.METADATA_RECORD:
            return abstain(
                ReasonCode.OUTSIDE_AGENT_SCOPE,
                "The Metadata Librarian drafts a metadata record, not a "
                f"{asked.document_kind.value}.",
            )
        requirements = asked.requirements
        if requirements is None:
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "Choose a repository first: the record has the properties it asks for.",
            )
        if requirements.conforms_to != DATACITE:
            return abstain(
                ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
                f"The librarian drafts DataCite records only, not {requirements.conforms_to}.",
            )

        record, filled = self._record(requirements, asked.inventory)
        filled += _from_researchers(record, asked.researchers)
        found = gaps(record)
        open_gaps = place(record, found, answers_by_question(asked.draft_answers))
        questions, suggested = self._questions(
            open_gaps, _facts(requirements, asked.inventory), ctx
        )
        required = sum(f.obligation == Obligation.REQUIRED for f in requirements.fields)
        statement = (
            f"A DataCite record for {requirements.repository_name} with the "
            f"{len(requirements.fields)} properties it asks for ({required} required), drafted "
            f"by rule. Filled: {', '.join(filled) or 'nothing'}"
            f"{_placed(len(found) - len(open_gaps))}. It asks "
            f"{_count(len(questions), 'question')}, one for each value left null. "
            f"{_how_suggested(suggested)}"
        )
        current = asked.current_version
        if current is not None:
            statement += f" It replaces version {current.version_ref.version} of the document."

        ref = input_ref(ctx)
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
                document_questions=questions,
                grounded_on=[ref],
            ),
            evidence=[input_evidence(ctx)],
            model_id=suggested.model_id,
            input_tokens=suggested.usage.input_tokens,
            output_tokens=suggested.usage.output_tokens,
            model_calls=tuple(suggested.calls.calls) if suggested.calls else (),
            prompts=dict(suggested.calls.prompts) if suggested.calls else {},
        )

    def _questions(
        self, open_gaps: Sequence[Gap], facts: Mapping[str, Any], ctx: RunContext
    ) -> tuple[list[DocumentQuestion], Suggestions]:
        """A question for each open gap, with the suggester's value where it offered one. The
        suggester is given the facts the record is drafted from and the questions on properties
        the rule table lets it suggest, never an answer or an earlier version
        (docs/specs/drafting.md, invariant 7)."""
        prompts = {prop: form.ask for prop, form in self.form.items()}
        questions = [ask(gap, prompts) for gap in open_gaps]
        asks = [
            Ask(q.question_id, gap.path, gap.prop, q.question_prompt, gap.qualifier)
            for gap, q in zip(open_gaps, questions, strict=True)
            if self.form.get(gap.prop, Form()).suggest and not gap.names_a_vocabulary
        ]
        suggested = self.suggester.suggest(facts, asks, ctx) if asks else Suggestions()
        return [
            q.model_copy(
                update={"suggested_answer": value, "suggestion_derivation": Derivation.MODEL}
            )
            if (value := suggested.answers.get(q.question_id))
            else q
            for q in questions
        ], suggested

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


def _from_researchers(record: dict[str, Any], researchers: list[ResearcherRecord]) -> list[str]:
    """Fill the creators, subjects and funding references the repository asks for from what the
    project's researchers kept of their ORCID records; returns the properties filled. A property
    the record does not have, because the repository does not ask for it, is left out."""
    filled: list[str] = []
    if not researchers:
        return filled
    if "creators" in record:
        record["creators"] = [_creator(r) for r in researchers]
        filled.append("creators")
    keywords = list(dict.fromkeys(k for r in researchers for k in r.keywords))
    if "subjects" in record and keywords:
        # The researchers' own words, after the entries the repository's vocabularies ask for.
        asked = [s for s in record["subjects"] if s.get("subjectScheme")]
        record["subjects"] = [*asked, *({"subject": k} for k in keywords)]
        filled.append("subjects")
    fundings = [f for r in researchers for f in r.fundings]
    if "fundingReferences" in record and fundings:
        record["fundingReferences"] = [_funding(f) for f in fundings]
        filled.append("fundingReferences")
    return filled


def _creator(researcher: ResearcherRecord) -> dict[str, Any]:
    """One researcher as a DataCite creator: their name, if they kept it (else null, for them to
    write), their ORCID iD, and the employers they kept that they still work for."""
    creator: dict[str, Any] = {
        "name": researcher.researcher_name,
        "nameType": "Personal",
        "nameIdentifiers": [
            {
                "nameIdentifier": researcher.orcid_id,
                "nameIdentifierScheme": "ORCID",
                "schemeUri": "https://orcid.org",
            }
        ],
    }
    current = [
        a
        for a in researcher.affiliations
        if a.affiliation_kind == AffiliationKind.EMPLOYMENT and a.end_year is None
    ]
    if current:
        creator["affiliation"] = [_affiliation(a) for a in current]
    return creator


def _affiliation(affiliation: Affiliation) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": affiliation.organisation_name}
    scheme = (affiliation.organisation_identifier_scheme or "").upper()
    if affiliation.organisation_identifier:
        entry["affiliationIdentifier"] = affiliation.organisation_identifier
        entry["affiliationIdentifierScheme"] = affiliation.organisation_identifier_scheme
        if scheme in SCHEME_URIS:
            entry["schemeUri"] = SCHEME_URIS[scheme]
    return entry


def _funding(funding: ResearcherFunding) -> dict[str, Any]:
    entry: dict[str, Any] = {"funderName": funding.funder_name}
    if funding.funder_identifier:
        entry["funderIdentifier"] = funding.funder_identifier
        scheme = (funding.funder_identifier_scheme or "").upper()
        entry["funderIdentifierType"] = FUNDER_SCHEMES.get(scheme, "Other")
    if funding.award_identifier:
        entry["awardNumber"] = funding.award_identifier
    entry["awardTitle"] = funding.funding_title
    return entry


def _facts(requirements: RepositoryRequirements, inventory: FileInventory | None) -> dict[str, Any]:
    """What a suggester is given: the repository, the properties it asks for, and the inventory's
    structure. Never the data, a description a person wrote, the researchers' records or an
    answer (docs/specs/drafting.md, invariant 4)."""
    files = inventory.inventory_files if inventory is not None else []
    return {
        "repository": requirements.repository_name,
        "conforms_to": requirements.conforms_to,
        "properties": [
            {
                "property": f.property,
                "obligation": f.obligation.value,
                **({"qualifier": f.qualifier} if f.qualifier else {}),
            }
            for f in requirements.fields
        ],
        "files": [
            {
                "path": f.file_path,
                "media_type": f.file_media_type,
                "size": f.file_size,
                "fields": [
                    {"name": c.name, "type": c.field_type, "format": c.field_format}
                    for c in f.file_fields
                ],
            }
            for f in files
        ],
    }


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _placed(n: int) -> str:
    return f", and {_count(n, 'answer')} you recorded" if n else ""


def _how_suggested(suggested: Suggestions) -> str:
    """The sentence saying whether a model suggested values, and what was not offered."""
    if suggested.model_id is None:
        return "No model suggested values."
    if suggested.unused is not None:
        return f"No suggestion is offered: {suggested.unused}."
    sentence = (
        f"A model suggested {_count(len(suggested.answers), 'value')}, offered beside its "
        "question and never written into the record."
    )
    if suggested.dropped:
        sentence += (
            f" {_count(len(suggested.dropped), 'suggestion')} not offered: "
            + "; ".join(suggested.dropped)
            + "."
        )
    return sentence


def build() -> MetadataLibrarian:
    """The librarian with no model; `factory.build` reads the agent's settings."""
    return MetadataLibrarian()
